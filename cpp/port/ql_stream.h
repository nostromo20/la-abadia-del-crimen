// ql_stream.h -- the bits of std::ofstream/ifstream that the fork's Serializar.cpp uses, over
// a memory buffer (the platform then writes the buffer to a file, or reads it back).
//
// COMPACT format (the default, 2026-10-05): the save must fit a microdrive cartridge that also
// holds the game. The fork's text ("1// dia\n" for every value: ~7 KB, 14 sectors) is replaced by
//   "ABQS", version byte 1, then every value Serializar writes, in order, as a 32-bit integer
//   zigzag-encoded (0,-1,1,-2.. -> 0,1,2,3..) in little-endian base-128 (7 bits a byte, the top bit
//   set on every byte but the last): most values take one byte.
// The comment strings and line ends Serializar writes are dropped, and its ignore() calls (which
// skipped them) do nothing. A file without the magic and version (an old text save, another
// version) fails at once: Juego::carga then puts the game back and says LOAD FAILED.
// Integers of every width go through int (32 bits on the QL and on the host alike), so both
// write identical files. tools/savefmt.py converts the old text saves.
//
// QL_SAVE_TEXT: the old text format (decimal numbers, comments kept), as before.
#ifndef QL_STREAM_H
#define QL_STREAM_H

#define QL_SAVE_MAGIC "ABQS"
#define QL_SAVE_VERSION 1

#ifndef QL_SAVE_TEXT
class QLOut
{
public:
	char *buf;
	int len, cap;
	bool failed;
	bool comentario;	// inside a "// ..." comment, up to its '\n': values there are dropped

	QLOut(char *b, int c) : buf(b), len(0), cap(c), failed(false), comentario(false)
	{
		*this << QL_SAVE_MAGIC;
		put((char)QL_SAVE_VERSION);
	}

	QLOut &put(char c) { if (len < cap) buf[len++] = c; else failed = true; return *this; }
	QLOut &raw(const char *s) { while (*s) put(*s++); return *this; }
	QLOut &operator<<(const char *s)
	{
		// the magic is the only string kept: Serializar's are comments and line ends. A value
		// written INSIDE a comment ("// SPRITE " << i << "\n": the text reader skips the whole
		// line) is not data: it is dropped too
		if (len == 0){ raw(s); return *this; }
		for (; *s; s++){
			if (s[0] == '/' && s[1] == '/') comentario = true;
			else if (*s == '\n') comentario = false;
		}
		return *this;
	}
	QLOut &value(int x)
	{
		if (comentario) return *this;
		unsigned int u = ((unsigned int)x << 1) ^ (unsigned int)(x >> 31);
		while (u >= 0x80){ put((char)((u & 0x7f) | 0x80)); u >>= 7; }
		put((char)u);
		return *this;
	}
	QLOut &operator<<(long v) { return value((int)v); }
	QLOut &operator<<(int v) { return value(v); }
	QLOut &operator<<(unsigned int v) { return value((int)v); }
	QLOut &operator<<(short v) { return value(v); }
	QLOut &operator<<(unsigned short v) { return value(v); }
	QLOut &operator<<(signed char v) { return value(v); }
	QLOut &operator<<(unsigned char v) { return value(v); }
	QLOut &operator<<(bool v) { return value(v ? 1 : 0); }
	bool fail() const { return failed; }
};

class QLIn
{
public:
	const char *buf;
	int pos, len;
	bool failed;

	QLIn(const char *b, int l) : buf(b), pos(0), len(l), failed(false)
	{
		const char *m = QL_SAVE_MAGIC;
		for (int i = 0; i < 4; i++) if (pos >= len || buf[pos++] != m[i]) failed = true;
		if (failed || pos >= len || (unsigned char)buf[pos++] != QL_SAVE_VERSION) failed = true;
	}

	bool readInt(int &v)
	{
		unsigned int u = 0;
		for (int sh = 0; sh < 35; sh += 7){
			if (pos >= len) return false;
			unsigned char c = (unsigned char)buf[pos++];
			u |= (unsigned int)(c & 0x7f) << sh;
			if (!(c & 0x80)){
				v = (int)(u >> 1) ^ -(int)(u & 1);
				return true;
			}
		}
		return false;
	}

	template <typename T> QLIn &operator>>(T &v)
	{
		int x;
		if (failed || !readInt(x)){ failed = true; return *this; }
		v = (T)x;
		return *this;
	}
	QLIn &operator>>(bool &v)
	{
		int x;
		if (failed || !readInt(x)){ failed = true; return *this; }
		v = (x != 0);
		return *this;
	}

	QLIn &ignore(long, int) { return *this; }	// (the text format's comments: none here)
	bool fail() const { return failed; }
};
#else	// QL_SAVE_TEXT

class QLOut
{
public:
	char *buf;
	int len, cap;
	bool failed;

	QLOut(char *b, int c) : buf(b), len(0), cap(c), failed(false) {}

	QLOut &put(char c) { if (len < cap) buf[len++] = c; else failed = true; return *this; }
	QLOut &operator<<(const char *s) { while (*s) put(*s++); return *this; }
	QLOut &operator<<(long v)
	{
		char t[12];
		int n = 0;
		unsigned long u = (v < 0) ? (unsigned long)(-v) : (unsigned long)v;
		if (v < 0) put('-');
		do { t[n++] = (char)('0' + u % 10); u /= 10; } while (u);
		while (n) put(t[--n]);
		return *this;
	}
	QLOut &operator<<(int v) { return *this << (long)v; }
	QLOut &operator<<(unsigned int v) { return *this << (long)v; }
	QLOut &operator<<(short v) { return *this << (long)v; }
	QLOut &operator<<(unsigned short v) { return *this << (long)v; }
	QLOut &operator<<(signed char v) { return *this << (long)v; }
	QLOut &operator<<(unsigned char v) { return *this << (long)v; }
	QLOut &operator<<(bool v) { return *this << (long)(v ? 1 : 0); }
	bool fail() const { return failed; }
};

class QLIn
{
public:
	const char *buf;
	int pos, len;
	bool failed;

	QLIn(const char *b, int l) : buf(b), pos(0), len(l), failed(false) {}

	bool readLong(long &v)
	{
		while (pos < len && (buf[pos] == ' ' || buf[pos] == '\n' || buf[pos] == '\r' || buf[pos] == '\t')) pos++;
		bool neg = false;
		if (pos < len && (buf[pos] == '-' || buf[pos] == '+')){ neg = buf[pos] == '-'; pos++; }
		if (pos >= len || buf[pos] < '0' || buf[pos] > '9') return false;
		long x = 0;
		while (pos < len && buf[pos] >= '0' && buf[pos] <= '9') x = x*10 + (buf[pos++] - '0');
		v = neg ? -x : x;
		return true;
	}

	template <typename T> QLIn &operator>>(T &v)
	{
		long x;
		if (failed || !readLong(x)){ failed = true; return *this; }
		v = (T)x;
		return *this;
	}
	QLIn &operator>>(bool &v)
	{
		long x;
		if (failed || !readLong(x)){ failed = true; return *this; }
		v = (x != 0);
		return *this;
	}

	QLIn &ignore(long n, int delim)
	{
		while (n-- > 0 && pos < len){
			if (buf[pos++] == delim) break;
		}
		return *this;
	}
	bool fail() const { return failed; }
};
#endif	// QL_SAVE_TEXT

#endif
