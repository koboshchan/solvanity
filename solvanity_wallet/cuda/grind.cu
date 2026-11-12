// MIT, Copyright 2026 koboshchan. Own search kernel; see vendor notices.
#include "vendor/fe.cu"
#include "vendor/ge.cu"
#include "vendor/sha512.cu"

__device__ void wallet_public(const unsigned char* seed, unsigned char* pub) {
    unsigned char digest[64];
    sha512(seed, 32, digest);
    digest[0] &= 248; digest[31] &= 63; digest[31] |= 64;
    ge_p3 point;
    ge_scalarmult_base(&point, digest);
    ge_p3_tobytes(pub, &point);
}
__device__ int wallet_base58(const unsigned char* pub, char* out) {
    const char* alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";
    unsigned char digits[45] = {};
    int used = 0, zeros = 0;
    while (zeros < 32 && pub[zeros] == 0) ++zeros;
    for (int i = zeros; i < 32; ++i) {
        unsigned int carry = pub[i];
        for (int j = 0; j < used; ++j) {
            carry += ((unsigned int)digits[j]) * 256;
            digits[j] = carry % 58; carry /= 58;
        }
        while (carry) { digits[used++] = carry % 58; carry /= 58; }
    }
    for (int i = 0; i < zeros; ++i) out[i] = '1';
    for (int i = 0; i < used; ++i) out[zeros+i] = alphabet[digits[used-1-i]];
    out[zeros+used] = 0;
    return zeros+used;
}
__device__ char wallet_fold(char c, int ignore_case) {
    return ignore_case && c >= 'A' && c <= 'Z' ? c + 32 : c;
}
extern "C" __global__ void wallet_derive(const unsigned char* seeds,
    unsigned char* pubs, unsigned long long n) {
    unsigned long long i = (unsigned long long)blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) wallet_public(seeds+32*i, pubs+32*i);
}
extern "C" __global__ void wallet_grind(const unsigned char* seeds,
    unsigned long long n, const char* prefix, int plen, const char* suffix,
    int slen, int ignore_case, unsigned int* found, unsigned int capacity,
    unsigned int* indices, unsigned char* pubs) {
    unsigned long long i = (unsigned long long)blockIdx.x * blockDim.x + threadIdx.x;
    if (i >= n) return;
    unsigned char pub[32]; char text[45];
    wallet_public(seeds+32*i, pub);
    int len = wallet_base58(pub, text);
    if (plen > len || slen > len) return;
    for (int j = 0; j < plen; ++j)
        if (wallet_fold(text[j], ignore_case) != wallet_fold(prefix[j], ignore_case)) return;
    for (int j = 0; j < slen; ++j)
        if (wallet_fold(text[len-slen+j], ignore_case) != wallet_fold(suffix[j], ignore_case)) return;
    unsigned int slot = atomicAdd(found, 1u);
    if (slot < capacity) {
        indices[slot] = (unsigned int)i;
        for (int j = 0; j < 32; ++j) pubs[32*slot+j] = pub[j];
    }
}
