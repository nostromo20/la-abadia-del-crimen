// ql_runtime.cpp -- the minimal C/C++ runtime the QL build needs (no libc, no libstdc++).
//
// operator new is a bump allocator over a static arena: the game creates all its objects
// once at start-up and never frees them, so delete is a no-op. ql_heap_used() reports the
// high-water mark for the harness.

#include <stddef.h>

#define QL_HEAP_SIZE (48*1024)

static long heap[QL_HEAP_SIZE/sizeof(long)];
static unsigned int heapUsed;

extern "C" void ql_fault(int code);   // asm: stores the fault word and halts

extern "C" unsigned int ql_heap_used(void) { return heapUsed; }

void *operator new(size_t n)
{
	n = (n + 3) & ~3u;
	if (heapUsed + n > QL_HEAP_SIZE) ql_fault(0x4f4f4d00);	// "OOM"
	void *p = (char *)heap + heapUsed;
	heapUsed += n;
	return p;
}

void *operator new[](size_t n) { return operator new(n); }
void operator delete(void *) {}
void operator delete[](void *) {}
void operator delete(void *, size_t) {}
void operator delete[](void *, size_t) {}

extern "C" void __cxa_pure_virtual(void) { ql_fault(0x50555245); }	// "PURE"
extern "C" int __cxa_atexit(void (*)(void *), void *, void *) { return 0; }
extern "C" void *__dso_handle = 0;

// memcpy/memmove/memset: the asm ones in src/libgcc68k.s (speed option 6, 2026-10-05). These C
// versions are their references: c_memcpy/c_memmove/c_memset in the dev build (tools/memtest.py),
// left out of the release; QL_C_MEMOPS (and vasm -DC_MEMOPS) makes them the real ones again.
#if defined(QL_C_MEMOPS) || !defined(QL_RELEASE)
#ifdef QL_C_MEMOPS
#define QL_MEMFN(n) n
#else
#define QL_MEMFN(n) c_##n
#endif
// copies in longs when source and destination have the same parity (the 68000 only needs
// even addresses for word/long access); forward copying is also correct for overlapping
// moves with d < s, backward for d > s
static void copyForward(unsigned char *dd, const unsigned char *ss, size_t n)
{
	if ((((unsigned long)dd ^ (unsigned long)ss) & 1) == 0){
		if (((unsigned long)dd & 1) && n){ *dd++ = *ss++; n--; }
		unsigned long *dl = (unsigned long *)dd;
		const unsigned long *sl = (const unsigned long *)ss;
		while (n >= 4){ *dl++ = *sl++; n -= 4; }
		dd = (unsigned char *)dl; ss = (const unsigned char *)sl;
	}
	while (n--) *dd++ = *ss++;
}

extern "C" void *QL_MEMFN(memcpy)(void *d, const void *s, size_t n)
{
	copyForward((unsigned char *)d, (const unsigned char *)s, n);
	return d;
}

extern "C" void *QL_MEMFN(memmove)(void *d, const void *s, size_t n)
{
	unsigned char *dd = (unsigned char *)d;
	const unsigned char *ss = (const unsigned char *)s;
	if (dd <= ss){
		copyForward(dd, ss, n);
	} else {
		dd += n; ss += n;
		if ((((unsigned long)dd ^ (unsigned long)ss) & 1) == 0){
			if (((unsigned long)dd & 1) && n){ *--dd = *--ss; n--; }
			unsigned long *dl = (unsigned long *)dd;
			const unsigned long *sl = (const unsigned long *)ss;
			while (n >= 4){ *--dl = *--sl; n -= 4; }
			dd = (unsigned char *)dl; ss = (const unsigned char *)sl;
		}
		while (n--) *--dd = *--ss;
	}
	return d;
}

extern "C" void *QL_MEMFN(memset)(void *d, int c, size_t n)
{
	unsigned char *dd = (unsigned char *)d;
	if (((unsigned long)dd & 1) && n){ *dd++ = (unsigned char)c; n--; }
	unsigned long v = (unsigned char)c;
	v |= v << 8; v |= v << 16;
	unsigned long *dl = (unsigned long *)dd;
	while (n >= 4){ *dl++ = v; n -= 4; }
	dd = (unsigned char *)dl;
	while (n--) *dd++ = (unsigned char)c;
	return d;
}
#endif

extern "C" size_t strlen(const char *s)
{
	size_t n = 0;
	while (s[n]) n++;
	return n;
}

extern "C" char *strncpy(char *d, const char *s, size_t n)
{
	size_t i = 0;
	for (; i < n && s[i]; i++) d[i] = s[i];
	for (; i < n; i++) d[i] = 0;
	return d;
}
