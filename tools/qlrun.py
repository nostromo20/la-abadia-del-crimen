#!/usr/bin/env python3
"""Headless QL runner for the hybrid image (unicorn, 68040 core standing in for the 68008).

Loads abadia_h_bin at a chosen address, CALLs it like SuperBASIC does, and emulates the few
QDOS traps the image uses -- all of which go through do_trap1 (qlstart.s), hooked by address:
  MT.DMODE ($10)  recorded
  MT.SUSJB ($08)  advances the frame counter in the header by D3 frames (the poll routine
                  is not run by the emulator)
  MT.LPOLL/RPOLL  recorded
  MT.IPCOM ($11)  KEYROW: returns the row bits for the scripted keys of the current tick
After every logic step the image passes harness_tick_done; the runner copies the state block
(header +32, 256 bytes) and moves the script on. Screens ($20000, 32 KB) can be dumped as PNG.

Unicorn has no 68008 timing and its 68040 tolerates unaligned word access; --align-check
adds a (slow) memory hook that reports word/long accesses to odd addresses.

  qlrun.py [--base 0x40000] [--ticks N] [--script f] [--state out] [--png-at t,t] [--align-check]
"""
import argparse, os, random, struct, sys, time

from unicorn import Uc, UcError, UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, UC_HOOK_CODE, UC_HOOK_MEM_READ, \
    UC_HOOK_MEM_WRITE, UC_HOOK_MEM_UNMAPPED, UC_HOOK_BLOCK
from unicorn import m68k_const as M
import unicorn

HERE = os.path.dirname(os.path.abspath(__file__))
QL = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import pngout

KEYS = ["UP", "DOWN", "LEFT", "RIGHT", "SPACE", "Q", "R", "S", "N", "ESC", "F1", "F2", "F3", "F5", "Y"]
# QL KEYROW matrix (row, bit) for each scripted key
KEYPOS = {"UP": (1, 2), "DOWN": (1, 7), "LEFT": (1, 1), "RIGHT": (1, 4), "SPACE": (1, 6),
          "ESC": (1, 3), "S": (3, 3), "R": (5, 4), "Q": (6, 3), "N": (7, 6), "F1": (0, 1), "F2": (0, 3),
          "F3": (0, 4), "F5": (0, 2), "Y": (6, 4)}
# QL key codes as typed into the keyboard queue (QEMU_KEYS mode)
KEYCODE = {"UP": 0xD0, "DOWN": 0xD8, "LEFT": 0xC0, "RIGHT": 0xC8, "SPACE": 0x20, "ESC": 0x1B,
           "S": 0x73, "R": 0x72, "Q": 0x71, "N": 0x6E, "F1": 0xE8, "F2": 0xEC,
           "F3": 0xF0, "F5": 0xF8, "Y": 0x79}
CON_ID = 0x0F0000                       # the image's "con_" keyboard channel
STATE_SIZE = 256
RET_SENTINEL = 0x000400
# load address: like a 640K QL, image + BSS must end below the QSound/expansion area at $C0000
BASE = 0x40000
RET_IRQ = 0x000600                      # (unused since the in-emulator stub)
STUB = 0x000700                         # in-emulator interrupt stub, see stub_code()
SAVE_SP = 0x0007F0
SYSVARS = 0x28000                       # fake QDOS system variables
SYS_STACK_LO, SYS_STACK_HI = 0x28400, 0x28600   # 512-byte "system stack" for the poll
GUARD = 0xA5
FRAME_CYCLES = 150000                   # 20 ms at 7.5 MHz (estimated 68008 cycles)
WATCHDOG_CYCLES = 60 * 7500000          # --realq: a minute without a logic step = hung

# registers a trap returns (the others in D1-D3/A0-A3 are clobbered in --realq mode)
TRAP1_OUT = {0x00: ("D1", "D2", "A0"), 0x08: (), 0x10: ("D1", "D2"), 0x11: ("D1",), 0x1C: (), 0x1D: ()}
TRAP23_OUT = {(2, 0x01): ("A0",), (2, 0x02): (), (2, 0x04): (), (3, 0x03): ("D1", "A1"), (3, 0x07): ("D1", "A1"),
              (3, 0x01): ("D1",)}
CLOBBERABLE = ("D1", "D2", "D3", "A0", "A1", "A2", "A3")


def load_symbols(path):
    syms = {}
    for line in open(path):
        p = line.split()
        if len(p) >= 2:
            syms[p[0]] = int(p[1], 16)
    return syms


def load_script(path):
    lines = []
    if not path:
        return lines
    for raw in open(path):
        raw = raw.split("#")[0].split()
        if len(raw) < 2:
            continue
        lines.append((int(raw[0]), int(raw[1]), set(raw[2:])))
    return lines


def keys_for(script, tick):
    k = set()
    for a, b, ks in script:
        if a <= tick <= b:
            k |= ks
    return k


class Runner:
    def __init__(self, image, syms, base, script, align_check=False, realq=False, sv164=0, seed=1):
        self.base = base
        self.realq = realq
        self.rng = random.Random(seed)
        self.cycles = 0
        self.tick_cycles = 0
        self.next_poll = FRAME_CYCLES
        self.pending_polls = 0
        self.in_poll = False
        self.poll_linked = False        # QDOS calls the poll routine only once MT.LPOLL linked it
        self.polls = 0
        self.poll_stack_max = 0
        self.poll_faults = []
        self.susjb_a1 = {}
        self.ay_port_writes = 0
        self.clobbers = 0
        self._cost = {}
        self.syms = syms
        self.script = script
        self.tick = 0
        self.states = []
        self.events = []
        self.stop_reason = None
        self.png_at = set()
        self.png_prefix = None
        self.max_ticks = 0
        self.trap_counts = {}
        self.tick_cb = None
        mu = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN)
        mu.ctl_set_cpu_model(M.UC_CPU_M68K_M68040)
        mu.mem_map(0, 0x100000)          # 1 MB: screen at $20000, image at base
        mu.mem_write(base, image)
        # harness flags (header +28): bit 0 state block, bit 1 skip the intro parchment
        mu.mem_write(base + 28, struct.pack(">I", (1 if os.environ.get("INTRO") else 3) |
                                            (0x20 if os.environ.get("FORCE_NIGHT") else 0) |
                                            (0x40 if os.environ.get("FORCE_MIRROR") else 0) |
                                            (0x80 if os.environ.get("HG_VERIFY") else 0) |
                                            # +30 bit 2: the nominal frame clock (as the oracle), unless
                                            # REALCLOCK (the frames the poll counts: tools/phrasetest.py)
                                            (0 if os.environ.get("REALCLOCK") else 0x400)))
        self.mu = mu
        self.image_len = len(image)
        # the save file name in the header (+1312, QDOS string), as the dev loaders set it
        if "hdr_savename" in syms:
            nm = os.environ.get("SAVENAME", "win1_abadia_sav").encode()
            mu.mem_write(base + syms["hdr_savename"], struct.pack(">H", len(nm)) + nm)
        self.fail_open_new = False      # harness: IO.OPEN of a new file fails (no device / write-protected)
        self.fail_write = False         # harness: IO.SSTRG fails
        # the drives that have a medium (a device's files: names starting with it); any other
        # device answers "not found" (-7), as QDOS does for an unknown device or an empty drive.
        # readonly: devices whose medium is write-protected (a new file: "read only", -20)
        self.devices = {"win1_", "win2_", "flp1_", "flp2_", "mdv1_", "mdv2_", "ram1_"}
        self.readonly = set()
        a = lambda n: base + syms[n]
        mu.hook_add(UC_HOOK_CODE, self.on_trap, begin=a("do_trap1"), end=a("do_trap1"))
        # two exact addresses (a range would also catch the rts between the two trap sites)
        mu.hook_add(UC_HOOK_CODE, self.on_trap23, begin=a("do_trap2"), end=a("do_trap2"))
        mu.hook_add(UC_HOOK_CODE, self.on_trap23, begin=a("do_trap3"), end=a("do_trap3"))
        self.files = {}          # emulated QDOS files: name -> bytes
        if os.environ.get("SAVEPRELOAD"):   # a save file already on the device (the script loads it: F2)
            self.files[os.environ.get("SAVENAME", "win1_abadia_sav")] = open(os.environ["SAVEPRELOAD"], "rb").read()
        self.chans = {}          # channel id -> [name, data, pos]
        mu.hook_add(UC_HOOK_CODE, self.on_tick, begin=a("harness_tick_done"), end=a("harness_tick_done"))
        mu.hook_add(UC_HOOK_CODE, self.on_fault, begin=a("ql_fault"), end=a("ql_fault"))
        mu.hook_add(UC_HOOK_CODE, self.on_return, begin=RET_SENTINEL, end=RET_SENTINEL)
        mu.hook_add(UC_HOOK_MEM_UNMAPPED, self.on_unmapped)
        mu.mem_write(SYSVARS + 0x164, struct.pack(">I", sv164 & 0xffffffff))
        # QEMU_KEYS=1: behave like Q-emuLator as seen on 2026-10-02 - KEYROW never shows a key,
        # held keys only arrive as characters on the image's con_ channel (IO.FBYTE)
        # Otherwise every key held at a step is typed once as that step starts (the image reads
        # keys only from its con_ channel unless built with USE_KEYROW=1; KEYROW is still answered).
        self.qemu_keys = bool(os.environ.get("QEMU_KEYS"))
        self.typed = []          # characters waiting on the con_ channel
        self.beeps = []          # MT.IPCOM BEEPs: (hdr_frames, 8 parameter bytes)
        self.beep_errors = []
        self.keyrows = []        # frames of the KEYROW reads (MT.IPCOM 9)
        self.ipc_order = []      # ("B"|"K", frame) in issue order
        self.con_open = False
        if 0xC0000 <= sv164 < 0x100000 and not sv164 & 1:
            # QSound present: AY.INIT at the vector is a stub that returns; ports are plain memory
            mu.mem_write(sv164, struct.pack(">H", 0x4E75))
        mu.hook_add(UC_HOOK_MEM_WRITE, self.on_ay_port, begin=0xC2000, end=0xC2003)
        if realq:
            mu.hook_add(UC_HOOK_BLOCK, self.on_block)
            code, self.stub_check, self.stub_end = self.stub_code()
            mu.mem_write(STUB, code)
            mu.hook_add(UC_HOOK_CODE, self.on_stub_check, begin=self.stub_check, end=self.stub_check)
            mu.hook_add(UC_HOOK_CODE, self.on_stub_end, begin=self.stub_end, end=self.stub_end)
        if align_check:
            mu.hook_add(UC_HOOK_MEM_READ | UC_HOOK_MEM_WRITE, self.on_mem)
        self.odd = []

    def r32(self, addr):
        return struct.unpack(">I", self.mu.mem_read(addr, 4))[0]

    def w32(self, addr, v):
        self.mu.mem_write(addr, struct.pack(">I", v & 0xffffffff))

    def on_mem(self, mu, access, addr, size, value, data):
        if size > 1 and addr & 1 and len(self.odd) < 50:
            self.odd.append((mu.reg_read(M.UC_M68K_REG_PC), addr, size))

    def on_unmapped(self, mu, access, addr, size, value, data):
        self.stop_reason = "unmapped access %06x at pc %06x" % (addr, mu.reg_read(M.UC_M68K_REG_PC))
        return False

    def on_return(self, mu, addr, size, data):
        self.stop_reason = "returned to BASIC (d0=%d)" % mu.reg_read(M.UC_M68K_REG_D0)
        mu.emu_stop()

    def on_fault(self, mu, addr, size, data):
        sp = mu.reg_read(M.UC_M68K_REG_A7)
        code = self.r32(sp + 4)
        self.stop_reason = "ql_fault %08x (%s)" % (code, struct.pack(">I", code))
        mu.emu_stop()

    # ---------------- real-QDOS model ----------------
    def on_ay_port(self, mu, access, addr, size, value, data):
        self.ay_port_writes += 1

    def clobber(self, outs):
        if not self.realq:
            return
        for r in CLOBBERABLE:
            if r not in outs:
                self.mu.reg_write(getattr(M, "UC_M68K_REG_" + r), 0xBAD00001 | (self.rng.randrange(1 << 16) << 1))
                self.clobbers += 1

    def block_cost(self, addr, size):
        c = self._cost.get((addr, size))
        if c is None:
            import cyclest
            code = bytes(self.mu.mem_read(addr, size))
            c = sum(cyclest.insn_cost(i) for i in cyclest.md.disasm(code, addr))
            self._cost[(addr, size)] = c
        return c

    def on_block(self, mu, addr, size, data):
        self.cycles += self.block_cost(addr, size)
        if self.cycles - self.tick_cycles > WATCHDOG_CYCLES:
            self.stop_reason = "HUNG: no logic step for %d s (estimated 68008 time), pc %06x" % (
                WATCHDOG_CYCLES // 7500000, addr - self.base)
            mu.emu_stop()
            return
        if not self.in_poll and self.cycles >= self.next_poll:
            self.next_poll += int(FRAME_CYCLES * self.rng.uniform(0.75, 1.25))
            if self.poll_linked:
                self.pending_polls += 1
                mu.emu_stop()

    def stub_code(self):
        L = lambda v: struct.pack(">I", v & 0xffffffff)
        W = lambda v: struct.pack(">H", v)
        c = W(0x42E7)                                   # move ccr,-(sp)
        c += W(0x48E7) + W(0xFFFE)                      # movem.l d0-d7/a0-a6,-(sp)
        c += W(0x23CF) + L(SAVE_SP)                     # move.l sp,SAVE_SP
        c += W(0x4FF9) + L(SYS_STACK_HI - 4)            # lea SYS_STACK_HI-4,sp
        c += W(0x47F9) + L(self.base + self.syms["poll_link"])   # lea poll_link,a3
        c += W(0x4DF9) + L(SYSVARS)                     # lea SYSVARS,a6
        c += W(0x4EB9) + L(self.base + self.syms["poll_routine"])  # jsr poll_routine
        check = STUB + len(c)
        c += W(0x4E71)                                  # nop (harness check point)
        c += W(0x2E79) + L(SAVE_SP)                     # movea.l SAVE_SP,sp
        c += W(0x4CDF) + W(0x7FFF)                      # movem.l (sp)+,d0-d7/a0-a6
        c += W(0x44DF)                                  # move (sp)+,ccr
        end = STUB + len(c)
        c += W(0x4E75)                                  # rts (to the interrupted PC)
        return c, check, end

    def on_stub_check(self, mu, addr, size, data):
        if mu.reg_read(M.UC_M68K_REG_A6) != SYSVARS:
            self.poll_faults.append("poll changed A6")
        stack = bytes(mu.mem_read(SYS_STACK_LO, SYS_STACK_HI - SYS_STACK_LO))
        used = next((SYS_STACK_HI - (SYS_STACK_LO + i) for i, b in enumerate(stack) if b != GUARD), 0)
        self.poll_stack_max = max(self.poll_stack_max, used)
        if stack[0] != GUARD:
            self.poll_faults.append("system stack overflow (512 bytes)")

    def on_stub_end(self, mu, addr, size, data):
        self.in_poll = False
        self.polls += 1

    REGS = ["D%d" % i for i in range(8)] + ["A%d" % i for i in range(8)] + ["PC", "SR"]

    def inject_poll(self):
        """one 50 Hz interrupt: push the interrupted PC, run the stub (which saves CCR and the
        registers itself), it returns to the interrupted PC"""
        mu = self.mu
        if self.qemu_keys:      # QDOS auto-repeat of the held keys
            self.autorepeat()
        pc = mu.reg_read(M.UC_M68K_REG_PC)
        sp = mu.reg_read(M.UC_M68K_REG_A7) - 4
        mu.mem_write(sp, struct.pack(">I", pc))
        mu.reg_write(M.UC_M68K_REG_A7, sp)
        mu.mem_write(SYS_STACK_LO, bytes([GUARD]) * (SYS_STACK_HI - SYS_STACK_LO))
        mu.reg_write(M.UC_M68K_REG_PC, STUB)
        self.in_poll = True

    def own_poll_stack_used(self):
        if "poll_stack" not in self.syms:
            return -1                   # builds before the poll routine had its own stack
        lo, hi = self.base + self.syms["poll_stack"], self.base + self.syms["poll_stack_top"]
        data = bytes(self.mu.mem_read(lo, hi - lo))
        return next((hi - (lo + i) for i, b in enumerate(data) if b != 0), 0)

    def on_trap(self, mu, addr, size, data):
        d0 = mu.reg_read(M.UC_M68K_REG_D0) & 0xff
        self.trap_counts[d0] = self.trap_counts.get(d0, 0) + 1
        if d0 == 0x08:      # MT.SUSJB: time passes
            d3 = mu.reg_read(M.UC_M68K_REG_D3) & 0xffff
            a1 = mu.reg_read(M.UC_M68K_REG_A1)
            if a1:          # QDOS clears the byte at (A1) when the job is released
                self.susjb_a1[a1] = self.susjb_a1.get(a1, 0) + 1
                if a1 < 0x100000:
                    mu.mem_write(a1, b"\0")
            if self.realq:
                if self.poll_linked:
                    self.pending_polls += max(1, d3)     # the frames pass as polls
            else:
                hf = self.base + 20
                self.w32(hf, self.r32(hf) + max(1, d3))
        elif d0 == 0x11:    # MT.IPCOM
            a3 = mu.reg_read(M.UC_M68K_REG_A3)
            blk = mu.mem_read(a3, 8)
            res = 0
            if blk[0] == 0x0A:      # IPC SOUND (BEEP): log frame + the 8 parameter bytes, check the block
                full = bytes(mu.mem_read(a3, 15))
                frame = self.r32(self.base + 20)
                self.beeps.append((frame, full[6:14]))
                if full[1] != 8 or full[2:6] != bytes([0, 0, 0xAA, 0xAA]) or full[14] != 0:
                    self.beep_errors.append("bad BEEP block %s" % full.hex())
                if mu.reg_read(M.UC_M68K_REG_A6) != SYSVARS or mu.reg_read(M.UC_M68K_REG_D3) & 0xffff:
                    self.beep_errors.append("BEEP without A6 = sysvars / D3 = 0")
                if self.in_poll:
                    self.beep_errors.append("BEEP from the poll interrupt")
            if blk[0] == 9:
                self.keyrows.append(self.r32(self.base + 20))
                self.ipc_order.append(("K", self.r32(self.base + 20)))
            elif blk[0] == 0x0A:
                self.ipc_order.append(("B", self.r32(self.base + 20)))
            if blk[0] == 9 and not self.qemu_keys:
                row = blk[6]
                for k in keys_for(self.script, self.tick):
                    r, b = KEYPOS[k]
                    if r == row:
                        res |= 1 << b
            mu.reg_write(M.UC_M68K_REG_D1, res)
        elif d0 == 0x00:    # MT.INF: fake system variables (QSound slot +$164 from --sv164)
            mu.reg_write(M.UC_M68K_REG_A0, SYSVARS)
            mu.reg_write(M.UC_M68K_REG_D2, int.from_bytes(os.environ.get("QDOS_VERSION", "1.60").encode()[:4], "big"))  # "1.60" (QDOS); qstest: SMSQ/E "3.38"
        elif d0 == 0x10:    # MT.DMODE
            self.events.append(("dmode", mu.reg_read(M.UC_M68K_REG_D1)))
            if mu.reg_read(M.UC_M68K_REG_D1) & 0xff == 0xff:
                mu.reg_write(M.UC_M68K_REG_D1, 8)          # read: the loader left Mode 8
        elif d0 == 0x1C:    # MT.LPOLL
            self.poll_linked = True
        elif d0 == 0x1D:    # MT.RPOLL
            self.poll_linked = False
        self.clobber(TRAP1_OUT.get(d0, ()))
        mu.reg_write(M.UC_M68K_REG_D0, 0)
        mu.reg_write(M.UC_M68K_REG_PC, addr + 2)     # skip the trap: the rts follows
        if self.pending_polls and not self.in_poll:
            mu.emu_stop()

    def qstr(self, addr):
        n = struct.unpack(">H", self.mu.mem_read(addr, 2))[0]
        return bytes(self.mu.mem_read(addr + 2, n)).decode("latin-1")

    def on_trap23(self, mu, addr, size, data):
        """trap #2 (IO.OPEN/CLOSE/DELET) and trap #3 (IO.FSTRG/SSTRG) on emulated files"""
        trap = 2 if addr == self.base + self.syms["do_trap2"] else 3
        d0 = mu.reg_read(M.UC_M68K_REG_D0) & 0xff
        err = 0
        if trap == 2 and d0 == 0x01 and self.qstr(mu.reg_read(M.UC_M68K_REG_A0)).lower().startswith("con_"):
            self.con_open = True                 # keyboard console channel
            mu.reg_write(M.UC_M68K_REG_A0, CON_ID)
        elif trap == 2 and d0 == 0x02 and mu.reg_read(M.UC_M68K_REG_A0) == CON_ID:
            self.con_open = False
        elif trap == 3 and d0 == 0x01 and mu.reg_read(M.UC_M68K_REG_A0) == CON_ID:   # IO.FBYTE
            if self.typed:
                mu.reg_write(M.UC_M68K_REG_D1, self.typed.pop(0))
            else:
                err = -1                         # not complete: nothing typed
        elif trap == 2 and d0 == 0x01:            # IO.OPEN
            name = self.qstr(mu.reg_read(M.UC_M68K_REG_A0)).lower()   # (QDOS names: any case)
            key = mu.reg_read(M.UC_M68K_REG_D3) & 0xff
            dev = name[:name.find("_") + 1] if "_" in name else ""
            if dev not in self.devices:
                err = -7                         # no such device / no medium in the drive
            elif key == 4:                       # a directory: the medium is there
                cid = 0x10000 + len(self.chans)
                self.chans[cid] = ["", bytearray(), 0]
                mu.reg_write(M.UC_M68K_REG_A0, cid)
            elif key in (0, 1) and name not in self.files:
                err = -7                         # not found
            elif key >= 2 and (self.fail_open_new or dev in self.readonly):
                err = -20                        # read only (write-protected cartridge)
            else:
                if key >= 2:
                    self.files[name] = b""
                cid = 0x10000 + len(self.chans)
                self.chans[cid] = [name, bytearray(self.files[name]), 0]
                mu.reg_write(M.UC_M68K_REG_A0, cid)
        elif trap == 2 and d0 == 0x02:          # IO.CLOSE
            cid = mu.reg_read(M.UC_M68K_REG_A0)
            ch = self.chans.pop(cid, None)
            if ch and ch[0]:
                self.files[ch[0]] = bytes(ch[1])
        elif trap == 2 and d0 == 0x04:          # IO.DELET
            self.files.pop(self.qstr(mu.reg_read(M.UC_M68K_REG_A0)).lower(), None)
        elif trap == 3 and d0 in (0x03, 0x07):  # IO.FSTRG / IO.SSTRG
            ch = self.chans[mu.reg_read(M.UC_M68K_REG_A0)]
            n = mu.reg_read(M.UC_M68K_REG_D2) & 0xffff
            a1 = mu.reg_read(M.UC_M68K_REG_A1)
            if d0 == 0x07 and self.fail_write:
                got = 0
                err = -11                        # drive full
            elif d0 == 0x07:
                ch[1] += bytes(mu.mem_read(a1, n))
                got = n
            else:
                chunk = bytes(ch[1][ch[2]:ch[2] + n])
                mu.mem_write(a1, chunk)
                ch[2] += len(chunk)
                got = len(chunk)
                if got < n:
                    err = -10                    # end of file
            mu.reg_write(M.UC_M68K_REG_D1, got)
            mu.reg_write(M.UC_M68K_REG_A1, a1 + got)
        self.clobber(TRAP23_OUT.get((trap, d0), ()))
        mu.reg_write(M.UC_M68K_REG_D0, err & 0xffffffff)
        mu.reg_write(M.UC_M68K_REG_PC, addr + 2)

    def autorepeat(self):
        """QEMU_KEYS: a key typed when it goes down, then again after the auto-repeat delay and every
        interval after that (QDOS's SV_ARDEL / SV_ARFRQ, which the game's ar_setup sets in the
        fake system variables; AUTOREPEAT_EVERY_FRAME=1: the old model, a character every frame)"""
        held = keys_for(self.script, self.tick)
        if os.environ.get("AUTOREPEAT_EVERY_FRAME"):
            self.type_keys(held)
            return
        hf = self.__dict__.setdefault("held_frames", {})
        ardel = struct.unpack(">H", bytes(self.mu.mem_read(SYSVARS + 0x8C, 2)))[0] or 15
        arfrq = struct.unpack(">H", bytes(self.mu.mem_read(SYSVARS + 0x8E, 2)))[0] or 2
        out = []
        for k in held:
            f = hf.get(k, -1) + 1
            hf[k] = f
            if f == 0 or (f >= ardel and (f - ardel) % arfrq == 0):
                out.append(k)
        for k in list(hf):
            if k not in held:
                del hf[k]
        if out:
            self.type_keys(sorted(out))

    def type_keys(self, keys):
        if self.con_open and len(self.typed) < 128:
            self.typed.extend(KEYCODE[k] for k in keys)

    def on_tick(self, mu, addr, size, data):
        st = bytes(mu.mem_read(self.base + 32, STATE_SIZE))
        self.states.append(st)
        self.tick_cycles = self.cycles
        if self.tick_cb:
            self.tick_cb(self)
        if self.tick in self.png_at and self.png_prefix:
            self.dump_png("%s_%05d.png" % (self.png_prefix, self.tick))
        self.tick += 1
        if not self.qemu_keys:  # every key held this step is typed once as the step starts
            self.type_keys(sorted(keys_for(self.script, self.tick)))
        if self.tick >= self.max_ticks:
            self.stop_reason = "tick limit"
            mu.emu_stop()

    def call(self, name, *args):
        """Calls a C function of the image (after a run has initialised it) and returns D0."""
        mu = self.mu
        sp = self.base - 0x400
        frame = struct.pack(">I", RET_SENTINEL) + b"".join(struct.pack(">I", a & 0xffffffff) for a in args)
        mu.mem_write(sp, frame)
        mu.reg_write(M.UC_M68K_REG_A7, sp)
        self.stop_reason = None
        mu.emu_start(self.base + self.syms[name], RET_SENTINEL)
        return mu.reg_read(M.UC_M68K_REG_D0)

    def report(self):
        print("real-QDOS model: %s; polls %d, system stack max %d bytes, own poll stack max %d bytes, "
              "poll faults %s, MT.SUSJB A1 bytes cleared %s, QSound port writes %d, trap clobbers %d"
              % ("on" if self.realq else "off", self.polls, self.poll_stack_max, self.own_poll_stack_used(),
                 self.poll_faults[:5] or "none",
                 {("%06x" % k): v for k, v in list(self.susjb_a1.items())[:6]} or "none",
                 self.ay_port_writes, self.clobbers))

    def screen(self):
        return bytes(self.mu.mem_read(0x20000, 0x8000))

    def dump_png(self, path, scale=2):
        pngout.ql_rows_to_png(path, pngout.ql_mode8_to_indices(self.screen()), scale)

    def run(self, ticks):
        mu = self.mu
        self.max_ticks = ticks
        sp = self.base - 0x100
        mu.mem_write(sp, struct.pack(">I", RET_SENTINEL))
        mu.mem_write(RET_SENTINEL, b"\x4e\x71\x4e\x71")
        mu.reg_write(M.UC_M68K_REG_A7, sp)
        mu.reg_write(M.UC_M68K_REG_PC, self.base)
        t0 = time.time()
        pc = self.base
        while self.stop_reason is None:
            try:
                mu.emu_start(mu.reg_read(M.UC_M68K_REG_PC), 0x7fffffff)
            except UcError as e:
                self.stop_reason = "unicorn error %s at pc %06x" % (e, mu.reg_read(M.UC_M68K_REG_PC))
            if self.stop_reason is None and self.pending_polls and not self.in_poll:
                self.pending_polls -= 1
                self.inject_poll()
                continue
            if self.stop_reason is None and self.in_poll:
                continue
            if self.stop_reason is None:
                self.stop_reason = "emulation stopped"
        return time.time() - t0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", default=os.path.join(QL, "abadia_h_bin"))
    ap.add_argument("--sym", default=os.path.join(QL, "build", "abadia_h.sym"))
    ap.add_argument("--base", default=hex(BASE))
    ap.add_argument("--ticks", type=int, default=100)
    ap.add_argument("--script")
    ap.add_argument("--state", help="write the per-tick state blocks here")
    ap.add_argument("--png-at", default="", help="comma-separated ticks to dump the screen")
    ap.add_argument("--png-prefix", default=os.path.join(QL, "build", "run", "ql"))
    ap.add_argument("--align-check", action="store_true")
    ap.add_argument("--realq", action="store_true", help="model real QDOS (poll interrupts, trap clobbers, A1)")
    ap.add_argument("--sv164", default="0", help="value in the QSound vector system variable")
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()

    image = open(a.image, "rb").read()
    syms = load_symbols(a.sym)
    base = int(a.base, 0)
    assert base % 4 == 0
    r = Runner(image, syms, base, load_script(a.script), a.align_check, a.realq, int(a.sv164, 0), a.seed)
    r.png_at = set(int(x) for x in a.png_at.split(",") if x)
    r.png_prefix = a.png_prefix
    dt = r.run(a.ticks)
    hdr = bytes(r.mu.mem_read(base, 32))
    fault = struct.unpack(">I", hdr[12:16])[0]
    heap = struct.unpack(">I", hdr[24:28])[0]
    print("stopped: %s after %d ticks (%.1f s), fault word %08x, heap used %d, traps %s"
          % (r.stop_reason, r.tick, dt, fault, heap, r.trap_counts))
    if r.odd:
        print("ODD ACCESSES:", ["pc %06x addr %06x size %d" % o for o in r.odd[:10]])
    r.report()
    if a.state:
        open(a.state, "wb").write(b"".join(r.states))
    return 0 if r.stop_reason in ("tick limit",) else 1


if __name__ == "__main__":
    sys.exit(main())
