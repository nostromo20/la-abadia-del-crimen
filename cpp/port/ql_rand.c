/* ql_rand.c -- glibc's TYPE_3 random() (additive feedback, degree 31), so that the QL build
 * and the PC oracle produce the same numbers as the fork did on Linux (srand(1); rand()). */
#include "ql_port.h"

static int r_state[34];
static int r_f, r_b;
static int r_init;

void ql_srand(unsigned int seed)
{
	int i;
	if (seed == 0) seed = 1;
	r_state[0] = (int)seed;
	for (i = 1; i < 31; i++){
		/* state[i] = (16807 * state[i-1]) % 2147483647 via Schrage, as glibc does */
		long hi = r_state[i - 1] / 127773;
		long lo = r_state[i - 1] % 127773;
		long word = 16807 * lo - 2836 * hi;
		if (word < 0) word += 2147483647;
		r_state[i] = (int)word;
	}
	r_f = 3; r_b = 0;
	r_init = 1;
	for (i = 0; i < 310; i++) ql_rand();
}

int ql_rand(void)
{
	unsigned int result;
	if (!r_init) ql_srand(1);
	r_state[r_f] = (int)((unsigned int)r_state[r_f] + (unsigned int)r_state[r_b]);
	result = ((unsigned int)r_state[r_f] >> 1) & 0x7fffffff;
	if (++r_f >= 31){ r_f = 0; ++r_b; }
	else if (++r_b >= 31) r_b = 0;
	return (int)result;
}
