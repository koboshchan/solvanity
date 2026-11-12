// Original SHA-256 and canonical base58 implementation.
// A candidate is SHA256(base[32] || UTF8(namespace) || hex16(counter) || owner[32]).
#ifdef SOLVANITY_CPU_TEST
#include <stdint.h>
#define __device__
#define __constant__
#define __global__
#define __forceinline__ inline
#else
typedef unsigned int uint32_t;
typedef unsigned long long uint64_t;
#endif
typedef unsigned char byte;
__device__ __constant__ uint32_t K[64] = {
0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2};
__device__ __forceinline__ uint32_t rr(uint32_t v, int n) { return (v>>n)|(v<<(32-n)); }
__device__ void seed_hash(const byte* base,const byte* owner,const byte* ns,int nslen,uint64_t counter,byte* out) {
    byte message[128] = {0};
    const char hex[] = "0123456789abcdef";
    int len=80+nslen;
    for(int i=0;i<32;i++) message[i]=base[i];
    for(int i=0;i<nslen;i++) message[32+i]=ns[i];
    for(int i=0;i<16;i++) message[32+nslen+i]=hex[(counter>>(60-4*i))&15];
    for(int i=0;i<32;i++) message[48+nslen+i]=owner[i];
    message[len]=128;
    message[126]=(byte)((len*8)>>8); message[127]=(byte)(len*8);
    uint32_t h[8]={0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19};
    for(int block=0;block<2;block++) {
        uint32_t w[64];
        for(int i=0;i<16;i++) {
            int j=block*64+i*4;
            w[i]=((uint32_t)message[j]<<24)|((uint32_t)message[j+1]<<16)|((uint32_t)message[j+2]<<8)|message[j+3];
        }
        for(int i=16;i<64;i++) {
            uint32_t s0=rr(w[i-15],7)^rr(w[i-15],18)^(w[i-15]>>3);
            uint32_t s1=rr(w[i-2],17)^rr(w[i-2],19)^(w[i-2]>>10);
            w[i]=w[i-16]+s0+w[i-7]+s1;
        }
        uint32_t a=h[0],b=h[1],c=h[2],d=h[3],e=h[4],f=h[5],g=h[6],v=h[7];
        for(int i=0;i<64;i++) {
            uint32_t s1=rr(e,6)^rr(e,11)^rr(e,25);
            uint32_t ch=(e&f)^((~e)&g), t1=v+s1+ch+K[i]+w[i];
            uint32_t s0=rr(a,2)^rr(a,13)^rr(a,22), maj=(a&b)^(a&c)^(b&c),t2=s0+maj;
            v=g;g=f;f=e;e=d+t1;d=c;c=b;b=a;a=t1+t2;
        }
        h[0]+=a;h[1]+=b;h[2]+=c;h[3]+=d;h[4]+=e;h[5]+=f;h[6]+=g;h[7]+=v;
    }
    for(int i=0;i<32;i++) out[i]=(byte)(h[i/4]>>(24-8*(i%4)));
}
__device__ int base58(const byte* digest,char* out) {
    const char alphabet[]="123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";
    uint32_t limbs[8];
    int zeros=0; while(zeros<32 && digest[zeros]==0) zeros++;
    for(int i=0;i<8;i++) limbs[i]=((uint32_t)digest[i*4]<<24)|((uint32_t)digest[i*4+1]<<16)|((uint32_t)digest[i*4+2]<<8)|digest[i*4+3];
    char reverse[44]; int n=0, first=0;
    while(first<8) {
        while(first<8 && limbs[first]==0) first++;
        if(first==8) break;
        uint64_t rem=0;
        for(int i=first;i<8;i++) {
            uint64_t cur=(rem<<32)|limbs[i];
            limbs[i]=(uint32_t)(cur/58); rem=cur%58;
        }
        reverse[n++]=alphabet[rem];
    }
    for(int i=0;i<zeros;i++) out[i]='1';
    for(int i=0;i<n;i++) out[zeros+i]=reverse[n-1-i];
    out[zeros+n]=0; return zeros+n;
}
__device__ char fold(char c,int insensitive) { return insensitive && c>='A' && c<='Z' ? c+32 : c; }
__device__ bool matches(const char* a,int len,const char* pre,int plen,const char* suf,int slen,int insensitive) {
    if(len<plen || len<slen) return false;
    for(int i=0;i<plen;i++) if(fold(a[i],insensitive)!=fold(pre[i],insensitive)) return false;
    for(int i=0;i<slen;i++) if(fold(a[len-slen+i],insensitive)!=fold(suf[i],insensitive)) return false;
    return true;
}
#ifndef SOLVANITY_CPU_TEST
extern "C" __global__ void grind(
    const byte* base,const byte* owner,const byte* ns,int nslen,uint64_t start,uint32_t count,
    const char* pre,int plen,const char* suf,int slen,int insensitive,
    uint32_t* hit_count,uint64_t* hits) {
    uint32_t i=blockIdx.x*blockDim.x+threadIdx.x;
    if(i>=count) return;
    byte digest[32]; char address[45];
    seed_hash(base,owner,ns,nslen,start+i,digest);
    int n=base58(digest,address);
    if(matches(address,n,pre,plen,suf,slen,insensitive)) {
        uint32_t slot=atomicAdd(hit_count,1U);
        hits[slot]=start+i; // capacity=count, so no hit can be silently lost
    }
}
extern "C" __global__ void vectors(
    const byte* base,const byte* owner,const byte* ns,int nslen,uint64_t start,uint32_t count,byte* out) {
    uint32_t i=blockIdx.x*blockDim.x+threadIdx.x;
    if(i<count) seed_hash(base,owner,ns,nslen,start+i,out+i*32);
}
#else
extern "C" void cpu_hash(const byte* base,const byte* owner,const byte* ns,int nslen,uint64_t counter,byte* out) {
    seed_hash(base,owner,ns,nslen,counter,out);
}
extern "C" int cpu_base58(const byte* digest,char* out) { return base58(digest,out); }
extern "C" int cpu_match(const char* a,int n,const char* p,int pn,const char* s,int sn,int ic) {return matches(a,n,p,pn,s,sn,ic);}
#endif
