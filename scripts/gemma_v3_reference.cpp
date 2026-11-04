// Independent official llama.cpp CPU reference: embedded tokens + full last-position logits.
#include "llama.h"
#include "nlohmann/json.hpp"
#include <fstream>
#include <iostream>
#include <vector>
#include <string>
#include <filesystem>
#include <chrono>
using json=nlohmann::json;
int main(int argc,char**argv){
 if(argc!=4){std::cerr<<"usage: reference model.gguf fixtures.json output_dir\n";return 2;}
 std::ifstream in(argv[2]);json fixtures;in>>fixtures;
 std::filesystem::create_directories(argv[3]);
 llama_backend_init();auto mp=llama_model_default_params();mp.n_gpu_layers=0;
 auto* model=llama_model_load_from_file(argv[1],mp);if(!model)return 3;
 auto* vocab=llama_model_get_vocab(model);int nv=llama_vocab_n_tokens(vocab);
 json rows=json::array();
 for(size_t i=0;i<fixtures.size();i++){
  std::string prompt=fixtures[i].at("prompt");
  std::vector<llama_token> ids(prompt.size()+32);
  int n=llama_tokenize(vocab,prompt.data(),prompt.size(),ids.data(),ids.size(),true,true);
  if(n<0){ids.resize(-n);n=llama_tokenize(vocab,prompt.data(),prompt.size(),ids.data(),ids.size(),true,true);}
  if(n<=0||n>512)return 4;ids.resize(n);
  auto cp=llama_context_default_params();cp.n_ctx=512;cp.n_batch=512;cp.n_ubatch=512;cp.n_threads=6;cp.n_threads_batch=6;cp.type_k=GGML_TYPE_F32;cp.type_v=GGML_TYPE_F32;cp.flash_attn_type=LLAMA_FLASH_ATTN_TYPE_DISABLED;
  auto*ctx=llama_init_from_model(model,cp);if(!ctx)return 5;
  auto batch=llama_batch_init(n,0,1);batch.n_tokens=n;
  for(int j=0;j<n;j++){batch.token[j]=ids[j];batch.pos[j]=j;batch.n_seq_id[j]=1;batch.seq_id[j][0]=0;batch.logits[j]=(j==n-1);}
  auto start=std::chrono::steady_clock::now();
  if(llama_decode(ctx,batch)!=0)return 6;
  auto*logits=llama_get_logits_ith(ctx,-1);if(!logits)return 7;
  std::string name="fixture_"+std::to_string(i)+".f32";
  std::ofstream out(std::filesystem::path(argv[3])/name,std::ios::binary);out.write(reinterpret_cast<char*>(logits),nv*sizeof(float));out.close();
  int top=0;for(int j=1;j<nv;j++)if(logits[j]>logits[top])top=j;
  double seconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();
  rows.push_back({{"id",fixtures[i].at("id")},{"tokens",ids},{"vocab_size",nv},{"logits_file",name},{"top1_id",top},{"seconds",seconds}});
  std::cout<<"completed fixture "<<i<<" tokens "<<n<<" top1 "<<top<<std::endl;
  llama_batch_free(batch);llama_free(ctx);
 }
 std::ofstream meta(std::filesystem::path(argv[3])/"reference.json");meta<<json({{"backend","official llama.cpp CPU"},{"kv_dtype","float32"},{"flash_attention",false},{"rows",rows}}).dump(2)<<"\n";
 llama_model_free(model);llama_backend_free();return 0;
}
