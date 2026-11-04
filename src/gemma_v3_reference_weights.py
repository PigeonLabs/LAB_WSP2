"""Temporary all-F32 GGUF for independent llama.cpp forward comparison.

No upstream code is downloaded or executed here. The exact source artifact is
hash-locked. Quantized tensors are dequantized in complete row chunks using
the same gguf implementation as the HF loader, and written without reordering.
This checks forward arithmetic independently, not dequantizer independence.
Root owns the actual ~19 GB conversion and deletion of this temporary file.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import time

import numpy as np

from .gemma_v3_engine import GGUF_SHA256, sha256_file


def _chunks(tensor, chunk_rows):
    import gguf
    if len(tensor.shape) < 2:
        yield np.ascontiguousarray(gguf.dequantize(tensor.data, tensor.tensor_type), dtype=np.float32)
    else:
        for start in range(0, int(tensor.shape[-1]), chunk_rows):
            yield np.ascontiguousarray(gguf.dequantize(tensor.data[start:start + chunk_rows], tensor.tensor_type), dtype=np.float32)


def _convert(source, destination, expected_sha256, chunk_rows=1024, progress=None):
    """Internal fixture-testable implementation; public converter locks the hash."""
    import gguf

    source, destination = Path(source), Path(destination)
    if chunk_rows < 1:
        raise ValueError("chunk_rows must be positive")
    if source.resolve() == destination.resolve():
        raise ValueError("Never overwrite source weights")
    partial = destination.with_name(destination.name + ".partial")
    receipt_path = destination.with_name(destination.name + ".json")
    if destination.exists() or partial.exists() or receipt_path.exists():
        raise FileExistsError("Destination, partial, or receipt exists; explicit cleanup is required")
    source_hash = sha256_file(source)
    if source_hash != expected_sha256:
        raise ValueError(f"Wrong source artifact: {source_hash}")
    start_time = time.monotonic()
    reader = gguf.GGUFReader(source)
    arch = reader.fields["general.architecture"].contents()
    destination.parent.mkdir(parents=True, exist_ok=True)
    writer = gguf.GGUFWriter(partial, arch=arch)
    skipped = []
    for key, field in reader.fields.items():
        if key.startswith("GGUF.") or key == "general.architecture":
            continue
        if key in ("general.file_type", "general.quantization_version", "general.quantized_by") or key.startswith("quantize."):
            skipped.append(key)
            continue
        value_type = field.types[0]
        subtype = field.types[1] if len(field.types) > 1 else None
        writer.add_key_value(key, field.contents(), value_type, subtype)
    writer.add_file_type(gguf.LlamaFileType.ALL_F32)
    writer.add_string("wsp2.reference.source_sha256", source_hash)
    writer.add_string("wsp2.reference.operation", "exact gguf.dequantize to float32; no transpose or rescale")
    expected_bytes = 0
    for tensor in reader.tensors:
        shape = tuple(int(v) for v in tensor.shape[::-1])
        nbytes = int(np.prod(shape)) * 4
        writer.add_tensor_info(tensor.name, shape, np.dtype(np.float32), nbytes)
        expected_bytes += nbytes
    writer.write_header_to_file()
    writer.write_kv_data_to_file()
    writer.write_ti_data_to_file()
    if writer.fout is None or len(writer.fout) != 1:
        raise RuntimeError("Reference conversion requires exactly one output shard")
    stream = writer.fout[0]
    checksums = {}
    try:
        for index, tensor in enumerate(reader.tensors):
            writer.write_padding(stream, stream.tell())
            checksum = hashlib.sha256()
            written = 0
            for array in _chunks(tensor, chunk_rows):
                raw = memoryview(array).cast("B")
                checksum.update(raw)
                array.tofile(stream)
                written += array.nbytes
            if written != int(np.prod(tensor.shape)) * 4:
                raise RuntimeError(f"Wrong dequantized byte count: {tensor.name}")
            writer.write_padding(stream, written)
            checksums[tensor.name] = checksum.hexdigest()
            if progress and index % 25 == 0:
                progress({"converted": index + 1, "total": len(reader.tensors), "tensor": tensor.name})
        stream.flush()
        os.fsync(stream.fileno())
    finally:
        writer.close()
    # Independent read-back of the serialized bytes, all tensors, not a sample.
    output = gguf.GGUFReader(partial)
    if len(output.tensors) != len(reader.tensors):
        raise RuntimeError("Serialized tensor count changed")
    for tensor in output.tensors:
        if tensor.tensor_type != gguf.GGMLQuantizationType.F32:
            raise RuntimeError(f"Reference output tensor is not F32: {tensor.name}")
        checksum = hashlib.sha256(memoryview(np.asarray(tensor.data)).cast("B")).hexdigest()
        if checksums.get(tensor.name) != checksum:
            raise RuntimeError(f"Serialized dequantization checksum mismatch: {tensor.name}")
    for key, field in reader.fields.items():
        if key.startswith("GGUF.") or key in skipped:
            continue
        if key not in output.fields or field.contents() != output.fields[key].contents():
            raise RuntimeError(f"Metadata changed: {key}")
    output_hash = sha256_file(partial)
    receipt = {
        "status": "VERIFIED_ALL_TENSOR_BYTES_AND_RETAINED_METADATA",
        "source": str(source), "source_sha256": source_hash,
        "destination": str(destination), "sha256": output_hash,
        "bytes": partial.stat().st_size, "tensor_bytes": expected_bytes,
        "tensor_count": len(reader.tensors), "dtype": "float32",
        "removed_quantization_metadata": skipped,
        "tensor_sha256": checksums,
        "elapsed_seconds": time.monotonic() - start_time,
        "engine_sha256": sha256_file(__file__),
        "limitation": "Shares gguf.dequantize with HF loader; tests forward implementation independently, not dequantizer correctness.",
    }
    del output
    partial.rename(destination)
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


def write_fp32_reference(source, destination, chunk_rows=1024, progress=None):
    return _convert(source, destination, GGUF_SHA256, chunk_rows, progress)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Create temporary independent-engine all-F32 GGUF; no GPU")
    parser.add_argument("--source", default="cache/gemma-v3/gemma-4-E2B-it-Q4_K_M.gguf")
    parser.add_argument("--output", required=True)
    parser.add_argument("--chunk-rows", type=int, default=1024)
    args = parser.parse_args()
    result = write_fp32_reference(args.source, args.output, args.chunk_rows, lambda x: print(json.dumps(x), flush=True))
    print(json.dumps({k: v for k, v in result.items() if k != "tensor_sha256"}, indent=2))


if __name__ == "__main__":
    main()
