"""Observe and intervene on the actual input of the MLP down projection."""
import torch
from torch.nn import functional as F


def sign_regime(gate, up):
    """0=++ 1=+- 2=-+ 3=--; exact zero belongs to a fifth neutral bin."""
    result = 2 * (gate < 0).to(torch.int8) + (up < 0).to(torch.int8)
    return torch.where((gate == 0) | (up == 0), torch.full_like(result, 4), result)


class SwiGLUHook:
    """Context-managed hook with last-call detached CPU records.

    positions is None for all positions, an integer for a common position, or
    a [batch] tensor/list for per-example positions. neurons defaults to all.
    Mean/patch replacements must broadcast to [batch, positions, neurons].
    A [batch, neurons] replacement is accepted for one position per example.
    Captured product is pre-intervention; modified_product is actual down input.
    """
    def __init__(self, mlp, neurons=None, positions=None, mode=None, replacement=None, scale=1.0, capture_contribution=True):
        if mode not in (None, "zero", "mean", "patch", "scale"):
            raise ValueError(f"Unknown intervention {mode}")
        if mode in ("mean", "patch") and replacement is None:
            raise ValueError("Mean/patch intervention requires a reference replacement")
        if mode == "scale" and not 0 <= scale <= 2:
            raise ValueError("Scaling must remain in the predeclared [0, 2] range")
        self.mlp, self.neurons, self.positions = mlp, neurons, positions
        self.mode, self.replacement, self.scale = mode, replacement, scale
        self.capture_contribution = capture_contribution
        self.records, self.handles, self._raw = {}, [], {}

    def __enter__(self):
        if self.handles:
            raise RuntimeError("Hook is already installed")
        self.handles = [
            self.mlp.gate_proj.register_forward_hook(self._capture("gate")),
            self.mlp.up_proj.register_forward_hook(self._capture("up")),
            self.mlp.down_proj.register_forward_pre_hook(self._down),
        ]
        return self

    def __exit__(self, *args):
        for handle in self.handles:
            handle.remove()
        self.handles.clear()
        self._raw.clear()

    def _capture(self, name):
        def capture(module, inputs, output):
            self._raw[name] = output.detach()
        return capture

    def _down(self, module, inputs):
        product = inputs[0]
        if product.ndim != 3:
            raise ValueError("Expected [batch, time, neurons] MLP input")
        gate, up = self._raw["gate"], self._raw["up"]
        if not torch.allclose(product.detach(), F.silu(gate) * up, atol=2e-5, rtol=2e-3):
            raise RuntimeError("Observed down input does not equal SiLU(gate) * up")
        b, t, n = product.shape
        neurons = torch.arange(n, device=product.device) if self.neurons is None else torch.as_tensor(self.neurons, device=product.device, dtype=torch.long).flatten()
        if len(neurons) != len(neurons.unique()) or bool(((neurons < 0) | (neurons >= n)).any()):
            raise ValueError("Neuron indices must be unique and in bounds")
        if self.positions is None:
            positions = torch.arange(t, device=product.device).expand(b, t)
        elif isinstance(self.positions, int):
            if not -t <= self.positions < t:
                raise IndexError("Position is out of bounds")
            positions = torch.full((b, 1), self.positions % t, device=product.device)
        else:
            positions = torch.as_tensor(self.positions, device=product.device, dtype=torch.long).reshape(b, 1)
            if bool(((positions < -t) | (positions >= t)).any()):
                raise IndexError("Position is out of bounds")
            positions = positions % t
        idx = (torch.arange(b, device=product.device)[:, None, None], positions[:, :, None], neurons[None, None, :])
        before = product[idx]
        changed = product
        if self.mode is not None:
            changed = product.clone()
            if self.mode == "zero":
                value = torch.zeros_like(before)
            elif self.mode == "scale":
                value = before * self.scale
            else:
                value = torch.as_tensor(self.replacement, device=product.device, dtype=product.dtype)
                if value.ndim == 2 and positions.shape[1] == 1 and value.shape == (b, len(neurons)):
                    value = value[:, None, :]
                value = torch.broadcast_to(value, before.shape)
            changed[idx] = value
        # Retain only selected positions/channels; no full activation history.
        self.records = {"gate": gate[idx].float().cpu(), "up": up[idx].float().cpu(),
                        "product": before.detach().float().cpu(),
                        "modified_product": changed[idx].detach().float().cpu(),
                        "sign_regime": sign_regime(gate[idx], up[idx]).cpu(),
                        "neurons": neurons.cpu(), "positions": positions.cpu()}
        with torch.no_grad():
            columns = module.weight[:, neurons].T.float()
            self.records["contribution_norm"] = (before.detach().float().abs() * columns.norm(dim=-1)).cpu()
            if self.capture_contribution:
                self.records["contribution"] = (before.detach().float()[..., None] * columns[None, None, :, :]).cpu()
        return (changed,) + inputs[1:]
