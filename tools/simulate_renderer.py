#!/usr/bin/env python3
"""Simulate the CPC bytecode rendering interpreter from La Abadia del Crimen.

Reads ABADIA1.BIN and executes the rendering bytecodes for each object type,
tracking all tile draws to determine which tiles each type renders and where.

Outputs diagnostic info to stdout and generates src/object_types.s with
the tile layout data for each object type.

Usage: python tools/simulate_renderer.py
"""

import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(PROJECT_DIR, "data")
SRC_DIR = os.path.join(PROJECT_DIR, "src")

# ABADIA1.BIN loads at CPC address $0100
ABADIA1_LOAD = 0x0100

# Object type pointer table at $156D in CPC address space
TYPE_TABLE_ADDR = 0x156D

# Maximum type byte value (types indexed by type_byte, stepping by 2)
# Table extends beyond $9E - rooms use types $A0, $A2, $A6
MAX_TYPE = 0xA8

# Maximum bytecode instructions per type to prevent infinite loops
MAX_INSTRUCTIONS = 2000

# Maximum recursion depth for $EC calls
MAX_DEPTH = 8

# Visible tile grid bounds (H=8..27, L=8..23)
H_MIN, H_MAX = 8, 27
L_MIN, L_MAX = 8, 23


class SimulationError(Exception):
    """Raised when simulation encounters an unrecoverable error."""
    pass


class BytecodeSimulator:
    """Simulates the CPC rendering bytecode interpreter."""

    def __init__(self, data):
        self.data = data  # raw ABADIA1.BIN contents
        self.data_len = len(data)
        self.max_cpc_addr = ABADIA1_LOAD + self.data_len - 1

    def cpc_to_file(self, addr):
        """Convert CPC address to file offset."""
        return addr - ABADIA1_LOAD

    def read_byte_at(self, cpc_addr):
        """Read a byte from CPC address space."""
        off = self.cpc_to_file(cpc_addr)
        if off < 0 or off >= self.data_len:
            raise SimulationError(
                f"Read out of range: CPC ${cpc_addr:04X} "
                f"(valid ${ABADIA1_LOAD:04X}-${self.max_cpc_addr:04X})")
        return self.data[off]

    def read_word_le(self, cpc_addr):
        """Read 16-bit little-endian word from CPC address space."""
        lo = self.read_byte_at(cpc_addr)
        hi = self.read_byte_at(cpc_addr + 1)
        return lo | (hi << 8)

    def simulate_type(self, type_idx):
        """Simulate rendering for a single object type.

        Returns: (list of (dH, dL, tile_index), error_msg or None)
        """
        # Read pointer table entry
        table_addr = TYPE_TABLE_ADDR + type_idx
        try:
            ptr = self.read_word_le(table_addr)
        except SimulationError:
            return [], f"Table entry ${table_addr:04X} out of range"

        if ptr == 0 or ptr < ABADIA1_LOAD or ptr > self.max_cpc_addr:
            return [], f"Invalid pointer ${ptr:04X}"

        # At the pointer: first 2 bytes = workspace data pointer
        try:
            workspace_data_ptr = self.read_word_le(ptr)
        except SimulationError:
            return [], f"Cannot read workspace ptr at ${ptr:04X}"

        # Bytecodes start at ptr+2
        bytecode_start = ptr + 2

        # Read 12 bytes of workspace from workspace_data_ptr
        workspace = bytearray(12)
        try:
            for i in range(12):
                workspace[i] = self.read_byte_at(workspace_data_ptr + i)
        except SimulationError:
            return [], f"Cannot read workspace at ${workspace_data_ptr:04X}"

        # Create execution state
        state = self._make_state(workspace, bytecode_start)

        # Execute
        tiles = []
        try:
            self._execute(state, tiles, depth=0)
        except SimulationError as e:
            # Return whatever tiles we got before the error
            return self._relativize_tiles(tiles, 16, 16), str(e)

        return self._relativize_tiles(tiles, 16, 16), None

    def _make_state(self, workspace, ix, fine_x=0, fine_y=0, height=0xFF):
        """Create a fresh interpreter state.

        fine_x, fine_y: CPC stores these as ext_6D, ext_6E via BC register.
            Top-level: BC = (fineY, fineX) from packed coords.
            $201A: LD ($1FDB),BC stores C=fineX=ext_6D, B=fineY=ext_6E.
        height: CPC stores at $1FDD. $FF = no projection, else = height value.

        CPC memory layout from $1FCF (workspace base):
          $1FCF-$1FDA (offset 0-11):  workspace bytes (from type data)
          $1FDB       (offset 12):    ext_6D = fineX (C register)
          $1FDC       (offset 13):    ext_6E = fineY (B register)
          $1FDD       (offset 14):    ext_6F = height
          $1FDE       (offset 15):    projection E = (h>>1)+H+L-15
          $1FDF       (offset 16):    projection D = 16+(h>>1)+H-L
        Param bytes $61-$6F access offsets 0-14 (no mirror).
        Param bytes $70-$81 access offsets 15-32 (with mirror XOR bit 0).
        """
        return {
            'H': 16,           # screen cursor (Z80 H register)
            'L': 16,           # screen cursor (Z80 L register)
            'IX': ix,          # bytecode program counter
            'workspace': bytearray(workspace),  # 12-byte workspace at $1FCF
            'ext_6D': fine_x & 0xFF,  # $1FDB (offset 12) - BC low = fineX
            'ext_6E': fine_y & 0xFF,  # $1FDC (offset 13) - BC high = fineY
            'ext_6F': height & 0xFF,  # $1FDD (offset 14) - height param
            'pos_stack': [],   # position stack for FC/FB
            'loop_stack': [],  # loop stack for FE/FD/FA: (ix, counter)
            'f5_direction': 1,    # +1 normally, -1 mirrored
            'f3_direction': -1,   # -1 normally, +1 mirrored
            'f8_step_direction': 1,  # +1 normally, -1 mirrored
            'draw_step_h': -1,    # self-modified DEC H at $211B
            'mirror_flag': 0,     # 0 normal, 1 mirrored
            'proj_E': 0,         # $1FDE (offset 15) - projection E register
            'proj_D': 0,         # $1FDF (offset 16) - projection D register
            'instruction_count': 0,
        }

    def _read_ix_byte(self, state):
        """Read next byte from bytecode stream and advance IX."""
        ix = state['IX']
        b = self.read_byte_at(ix)
        state['IX'] = ix + 1
        return b

    def _peek_ix_byte(self, state):
        """Peek at next byte without advancing IX."""
        return self.read_byte_at(state['IX'])

    def _read_param(self, state):
        """Parameter reader ($2214).

        Returns (value, workspace_addr_or_None).
        workspace_addr is the index into workspace[] if the param references
        a workspace slot, or None for literals.
        """
        b = self._read_ix_byte(state)

        if b < 0x60:
            # Literal value 0-95
            return b, None

        if b == 0x82:
            # Next byte is literal
            val = self._read_ix_byte(state)
            return val, None

        if 0x61 <= b <= 0x6C:
            # Workspace[b - 0x61]
            idx = b - 0x61
            return state['workspace'][idx], idx

        if b == 0x6D:
            return state['ext_6D'], '6D'

        if b == 0x6E:
            return state['ext_6E'], '6E'

        if b == 0x6F:
            return state['ext_6F'], '6F'

        if 0x70 <= b <= 0x81:
            # Mirror workspace: XOR bit 0 swaps pairs (self-modifying
            # XOR at CPC $222F, patched to $01 in mirror mode).
            # Then SUB $61 gives offset from workspace base $1FCF.
            lookup_val = b
            if state['mirror_flag']:
                lookup_val = b ^ 0x01
            offset = lookup_val - 0x61
            if 0 <= offset < 12:
                return state['workspace'][offset], offset
            elif offset == 12:
                return state['ext_6D'], '6D'
            elif offset == 13:
                return state['ext_6E'], '6E'
            elif offset == 14:
                return state['ext_6F'], '6F'
            elif offset == 15:  # $1FDE - projection E register
                return state['proj_E'], 'proj_E'
            elif offset == 16:  # $1FDF - projection D register
                return state['proj_D'], 'proj_D'
            else:
                # Offsets 17+: dispatch table at $1FE0+ (unlikely used)
                return 0, None

        # Unknown param byte - treat as literal 0
        return 0, None

    def _eval_expression(self, state):
        """Expression evaluator ($2166).

        Read first param, then check for expression continuation.
        Returns final accumulated value.
        """
        val, _ = self._read_param(state)
        return self._eval_expression_chain(state, val)

    def _eval_expression_chain(self, state, accum):
        """Continue expression evaluation after initial param read.

        The chain works by peeking at the next byte:
        - >= $C8: expression complete (these are opcodes)
        - == $84: consume it, negate accumulator, continue
        - anything else: the byte is directly read by the param reader
          (no separate connector byte), ADD result to accumulator, continue
        """
        while True:
            # Peek at next byte
            try:
                nxt = self._peek_ix_byte(state)
            except SimulationError:
                return accum

            if nxt >= 0xC8:
                # Expression done (opcode territory)
                return accum

            if nxt == 0x84:
                # Negate accumulator
                self._read_ix_byte(state)  # consume $84
                accum = (-accum) & 0xFF
                continue

            # The peeked byte IS the next param (no connector to skip).
            # read_param will consume it as part of reading the parameter.
            val2, _ = self._read_param(state)
            accum = (accum + val2) & 0xFF
            continue

    def _read_param_with_expression(self, state):
        """Read a parameter and evaluate any following expression chain."""
        val, addr = self._read_param(state)
        val = self._eval_expression_chain(state, val)
        return val, addr

    def _draw_tile(self, state, tile_index, tiles):
        """Record a tile draw at the current (H, L) position.

        Clips to visible bounds H=8..27, L=8..23.
        """
        h = state['H']
        l = state['L']
        if H_MIN <= h <= H_MAX and L_MIN <= l <= L_MAX:
            tiles.append((h, l, tile_index))

    def _draw_helper(self, state, tiles, caller_step):
        """Draw helper ($20FC).

        caller_step is a function that applies the post-draw step to state.
        Reads tile index, then handles continuation bytes.
        """
        while True:
            # Read tile index via param reader
            tile_val, _ = self._read_param(state)
            tile_index = tile_val & 0xFF

            # Peek next byte
            try:
                nxt = self._peek_ix_byte(state)
            except SimulationError:
                self._draw_tile(state, tile_index, tiles)
                caller_step(state)
                return

            if nxt >= 0xC8:
                # Opcode: draw tile, apply step, return
                self._draw_tile(state, tile_index, tiles)
                caller_step(state)
                return
            elif nxt == 0x80:
                # Draw tile, apply step, continue reading
                self._read_ix_byte(state)  # consume $80
                self._draw_tile(state, tile_index, tiles)
                caller_step(state)
                continue
            elif nxt == 0x81:
                # Draw tile WITHOUT stepping, continue reading
                self._read_ix_byte(state)  # consume $81
                self._draw_tile(state, tile_index, tiles)
                continue
            else:
                # consume separator, read repeat count
                self._read_ix_byte(state)  # consume separator
                repeat_val, _ = self._read_param(state)
                repeat_count = repeat_val & 0xFF
                # Draw tile repeat_count times with stepping
                for _ in range(repeat_count):
                    self._draw_tile(state, tile_index, tiles)
                    caller_step(state)
                # Peek next byte
                try:
                    nxt2 = self._peek_ix_byte(state)
                except SimulationError:
                    return
                if nxt2 >= 0xC8:
                    return
                else:
                    self._read_ix_byte(state)  # consume separator
                    continue

    def _step_dec_h(self, state):
        """Post-draw step: H -= 1."""
        state['H'] = (state['H'] - 1) & 0xFF

    def _step_inc_l_f8(self, state):
        """Post-draw step: L += f8_step_direction."""
        state['L'] = (state['L'] + state['f8_step_direction']) & 0xFF

    def _step_dec_l(self, state):
        """Post-draw step: L -= 1."""
        state['L'] = (state['L'] - 1) & 0xFF

    def _skip_to_matching_fa(self, state):
        """Skip forward past matching $FA (for false FE/FD branches).

        Track nesting: each FE/FD increases nesting, each FA decreases.
        """
        nesting = 1
        safety = 0
        while nesting > 0 and safety < MAX_INSTRUCTIONS:
            safety += 1
            b = self._read_ix_byte(state)
            if b == 0xFE or b == 0xFD:
                nesting += 1
            elif b == 0xFA:
                nesting -= 1
            elif b == 0xFF:
                # Hit end of bytecodes - stop
                break
        if safety >= MAX_INSTRUCTIONS:
            raise SimulationError("Runaway skip_to_FA")

    def _store_workspace(self, state, addr, value):
        """Store a value to a workspace slot identified by addr."""
        if addr is None:
            return
        if isinstance(addr, int):
            if 0 <= addr < 12:
                state['workspace'][addr] = value & 0xFF
        elif addr == '6D':
            state['ext_6D'] = value & 0xFF
        elif addr == '6E':
            state['ext_6E'] = value & 0xFF
        elif addr == '6F':
            state['ext_6F'] = value & 0xFF
        elif addr == 'proj_E':
            state['proj_E'] = value & 0xFF
        elif addr == 'proj_D':
            state['proj_D'] = value & 0xFF

    def _load_workspace(self, state, addr):
        """Load a value from a workspace slot identified by addr."""
        if addr is None:
            return 0
        if isinstance(addr, int):
            if 0 <= addr < 12:
                return state['workspace'][addr]
            return 0
        elif addr == '6D':
            return state['ext_6D']
        elif addr == '6E':
            return state['ext_6E']
        elif addr == '6F':
            return state['ext_6F']
        elif addr == 'proj_E':
            return state['proj_E']
        elif addr == 'proj_D':
            return state['proj_D']
        return 0

    def _execute(self, state, tiles, depth):
        """Execute bytecodes from current IX until $FF or error."""
        if depth > MAX_DEPTH:
            raise SimulationError(f"Recursion depth exceeded ({depth})")

        while state['instruction_count'] < MAX_INSTRUCTIONS:
            state['instruction_count'] += 1

            opcode = self._read_ix_byte(state)

            if opcode == 0xFF:
                # END - reset direction state
                state['f5_direction'] = 1
                state['f3_direction'] = -1
                state['f8_step_direction'] = 1
                state['mirror_flag'] = 0
                return

            elif opcode == 0xFE:
                # IF workspace[$6D] != 0
                val = state['ext_6D']
                if val != 0:
                    # Execute as nested block with loop counter
                    state['loop_stack'].append((state['IX'], val))
                else:
                    # Skip to matching $FA
                    self._skip_to_matching_fa(state)

            elif opcode == 0xFD:
                # IF workspace[$6E] != 0
                val = state['ext_6E']
                if val != 0:
                    state['loop_stack'].append((state['IX'], val))
                else:
                    self._skip_to_matching_fa(state)

            elif opcode == 0xFC:
                # PUSH position
                state['pos_stack'].append((state['H'], state['L']))

            elif opcode == 0xFB:
                # POP position
                if state['pos_stack']:
                    state['H'], state['L'] = state['pos_stack'].pop()

            elif opcode == 0xFA:
                # LOOP END
                if state['loop_stack']:
                    ix_start, counter = state['loop_stack'][-1]
                    counter -= 1
                    if counter > 0:
                        state['loop_stack'][-1] = (ix_start, counter)
                        state['IX'] = ix_start
                    else:
                        state['loop_stack'].pop()
                # If no loop stack entry, just continue

            elif opcode == 0xF9:
                # DRAW + DEC H
                self._draw_helper(state, tiles, self._step_dec_h)

            elif opcode == 0xF8:
                # DRAW + STEP L in f8_direction
                self._draw_helper(state, tiles, self._step_inc_l_f8)

            elif opcode == 0xEB:
                # DRAW + DEC L
                self._draw_helper(state, tiles, self._step_dec_l)

            elif opcode == 0xF7:
                # SET WORKSPACE
                # Peek first byte (before consuming) to check < $70
                first_byte = self._peek_ix_byte(state)
                is_low = (first_byte < 0x70)
                # Read param1 (destination)
                val1, dest_addr = self._read_param(state)
                # Read param2 (value) + expression chain
                val2, _ = self._read_param(state)
                final_value = self._eval_expression_chain(state, val2)
                final_value = final_value & 0xFF

                if is_low:
                    # Always store
                    self._store_workspace(state, dest_addr, final_value)
                else:
                    # Only store if current value at destination is non-zero
                    current = self._load_workspace(state, dest_addr)
                    if current != 0:
                        if final_value >= 100:
                            final_value = 0
                        self._store_workspace(state, dest_addr, final_value)

            elif opcode == 0xF6:
                # INC H
                state['H'] = (state['H'] + 1) & 0xFF

            elif opcode == 0xF5:
                # STEP L POS (f5_direction)
                state['L'] = (state['L'] + state['f5_direction']) & 0xFF

            elif opcode == 0xF4:
                # DEC H
                state['H'] = (state['H'] - 1) & 0xFF

            elif opcode == 0xF3:
                # STEP L NEG (f3_direction)
                state['L'] = (state['L'] + state['f3_direction']) & 0xFF

            elif opcode == 0xF2:
                # ADD TO H
                val = self._eval_expression(state)
                # Treat as signed byte for addition
                if val > 127:
                    val -= 256
                state['H'] = (state['H'] + val) & 0xFF

            elif opcode == 0xF1:
                # ADD TO L
                val = self._eval_expression(state)
                if val > 127:
                    val -= 256
                state['L'] = (state['L'] + val) & 0xFF

            elif opcode == 0xF0:
                # INC workspace[$6D]
                state['ext_6D'] = (state['ext_6D'] + 1) & 0xFF

            elif opcode == 0xEF:
                # INC workspace[$6E]
                state['ext_6E'] = (state['ext_6E'] + 1) & 0xFF

            elif opcode == 0xEE:
                # DEC workspace[$6D]
                state['ext_6D'] = (state['ext_6D'] - 1) & 0xFF

            elif opcode == 0xED:
                # DEC workspace[$6E]
                state['ext_6E'] = (state['ext_6E'] - 1) & 0xFF

            elif opcode == 0xEC:
                # CALL BLOCK (render sub-object) - loads NEW workspace
                # EC handler at CPC $21B4: JP $1BBC which copies 12 bytes
                # from the sub-object's workspace pointer to $1FCF.
                self._handle_ec(state, tiles, depth, copy_workspace=True)

            elif opcode == 0xE4:
                # CALL BLOCK variant - keeps CURRENT workspace
                # E4 handler at CPC $21AA: sets $1FCE=1, JP $1BB9 which
                # skips the LDIR workspace copy. The sub-call inherits
                # the caller's workspace, so workspace references ($61-$6C)
                # read from the parent's tiles, not the sub-object's.
                # E4 also sets $1FCE flag which suppresses direction reset
                # in $FF END (but state is fully restored anyway at $21F0).
                self._handle_ec(state, tiles, depth, copy_workspace=False)

            elif opcode == 0xEA:
                # JUMP - read 2-byte address
                target = self._read_ix_byte(state) | (self._read_ix_byte(state) << 8)
                if target < ABADIA1_LOAD or target > self.max_cpc_addr:
                    raise SimulationError(
                        f"JUMP to ${target:04X} outside range")
                state['IX'] = target

            elif opcode == 0xE9:
                # MIRROR MODE SET (not toggle!)
                # CPC E9 handler at $218D unconditionally writes mirror
                # values to self-modifying code locations:
                #   $2052 (F5 dir) = $2D (DEC L)
                #   $20F8 (F8 dir) = $2D (DEC L)
                #   $2058 (F3 dir) = $2C (INC L)
                #   $2230 (mirror XOR) = $01
                # The $FF END handler resets these to non-mirror state.
                state['f5_direction'] = -1
                state['f3_direction'] = 1
                state['f8_step_direction'] = -1
                state['mirror_flag'] = 1

            else:
                # Unknown opcode - might be data or unhandled opcode
                # Opcodes below $C8 would have been consumed as parameters
                # For safety, if we hit something unexpected in opcode range, stop
                if opcode >= 0xC8:
                    raise SimulationError(
                        f"Unknown opcode ${opcode:02X} at "
                        f"IX=${state['IX'] - 1:04X}")
                else:
                    # This shouldn't happen in normal flow since all bytes < $C8
                    # in opcode position would be odd. Treat as end.
                    raise SimulationError(
                        f"Unexpected byte ${opcode:02X} in opcode position "
                        f"at IX=${state['IX'] - 1:04X}")

        raise SimulationError("Instruction limit reached")

    def _handle_ec(self, state, tiles, depth, copy_workspace=True):
        """Handle $EC/$E4 (CALL BLOCK) - render sub-object.

        copy_workspace: True for $EC (load new workspace from sub-object),
                       False for $E4 (keep current workspace).
        CPC $EC at $21B4 -> JP $1BBC (LDIR copies 12 bytes to $1FCF).
        CPC $E4 at $21AA -> JP $1BB9 (JR skips LDIR, workspace unchanged).
        """
        # Read 2-byte address from bytecodes
        addr_lo = self._read_ix_byte(state)
        addr_hi = self._read_ix_byte(state)
        sub_addr = addr_lo | (addr_hi << 8)

        if sub_addr < ABADIA1_LOAD or sub_addr > self.max_cpc_addr:
            raise SimulationError(
                f"EC target ${sub_addr:04X} outside range")

        # At sub_addr: read 2-byte pointer to workspace+bytecode data
        sub_ptr = self.read_word_le(sub_addr)
        if sub_ptr < ABADIA1_LOAD or sub_ptr > self.max_cpc_addr:
            raise SimulationError(
                f"EC sub-pointer ${sub_ptr:04X} outside range")

        # Save ALL state (including IX - the parent's continuation point)
        saved_state = {
            'IX': state['IX'],  # parent resumes here after sub-object
            'H': state['H'],
            'L': state['L'],
            'workspace': bytearray(state['workspace']),
            'ext_6D': state['ext_6D'],
            'ext_6E': state['ext_6E'],
            'ext_6F': state['ext_6F'],
            'f5_direction': state['f5_direction'],
            'f3_direction': state['f3_direction'],
            'f8_step_direction': state['f8_step_direction'],
            'mirror_flag': state['mirror_flag'],
            'proj_E': state['proj_E'],
            'proj_D': state['proj_D'],
            'pos_stack': list(state['pos_stack']),
            'loop_stack': list(state['loop_stack']),
        }

        if copy_workspace:
            # $EC: Load new workspace (12 bytes from sub_ptr)
            for i in range(12):
                state['workspace'][i] = self.read_byte_at(sub_ptr + i)
        # $E4: workspace stays unchanged (sub-call inherits caller's)

        # Bytecodes for sub-object start at sub_addr+2
        state['IX'] = sub_addr + 2

        # Clear loop/position stacks for sub-object
        state['pos_stack'] = []
        state['loop_stack'] = []

        # Isometric projection — CPC $1FB8.
        # Computes depth values stored at $1FDE/$1FDF for grid cell z-ordering.
        # Does NOT modify HL (cursor). Sub-object inherits parent's cursor.
        height = state['ext_6F']
        h = state['H']
        l = state['L']
        if height != 0xFF:
            half_h = height // 2
            state['proj_E'] = (half_h + h + l - 15) & 0xFF   # E → $1FDE
            state['proj_D'] = (16 + half_h + h - l) & 0xFF   # D → $1FDF

        # Execute sub-object bytecodes recursively
        self._execute(state, tiles, depth + 1)

        # Restore ALL state (including IX to resume parent execution)
        state['IX'] = saved_state['IX']
        state['H'] = saved_state['H']
        state['L'] = saved_state['L']
        state['workspace'] = saved_state['workspace']
        state['ext_6D'] = saved_state['ext_6D']
        state['ext_6E'] = saved_state['ext_6E']
        state['ext_6F'] = saved_state['ext_6F']
        state['f5_direction'] = saved_state['f5_direction']
        state['f3_direction'] = saved_state['f3_direction']
        state['f8_step_direction'] = saved_state['f8_step_direction']
        state['mirror_flag'] = saved_state['mirror_flag']
        state['proj_E'] = saved_state['proj_E']
        state['proj_D'] = saved_state['proj_D']
        state['pos_stack'] = saved_state['pos_stack']
        state['loop_stack'] = saved_state['loop_stack']

    def _relativize_tiles(self, tiles, ref_h, ref_l):
        """Convert absolute (H, L, tile) to relative (dH, dL, tile)."""
        return [(h - ref_h, l - ref_l, t) for h, l, t in tiles]

    def simulate_type_at_position(self, type_idx, base_h, base_l,
                                   fine_x=0, fine_y=0, height=0xFF):
        """Simulate rendering for a type at a specific grid position.

        CPC rendering state at bytecode entry:
          HL = (base_h, base_l) = cursor (coarseY, coarseX)
          ext_6D = fine_x (from packed_x >> 5 & 7)
          ext_6E = fine_y (from packed_y >> 5 & 7)
          ext_6F = height ($FF if no extra byte, else extra byte value)

        Returns: (list of (H, L, tile_index), error_msg or None)
        Positions are absolute grid coordinates (not relativized).
        """
        table_addr = TYPE_TABLE_ADDR + type_idx
        try:
            ptr = self.read_word_le(table_addr)
        except SimulationError:
            return [], f"Table entry ${table_addr:04X} out of range"

        if ptr == 0 or ptr < ABADIA1_LOAD or ptr > self.max_cpc_addr:
            return [], f"Invalid pointer ${ptr:04X}"

        try:
            workspace_data_ptr = self.read_word_le(ptr)
        except SimulationError:
            return [], f"Cannot read workspace ptr at ${ptr:04X}"

        bytecode_start = ptr + 2

        workspace = bytearray(12)
        try:
            for i in range(12):
                workspace[i] = self.read_byte_at(workspace_data_ptr + i)
        except SimulationError:
            return [], f"Cannot read workspace at ${workspace_data_ptr:04X}"

        state = self._make_state(workspace, bytecode_start,
                                 fine_x=fine_x, fine_y=fine_y,
                                 height=height)
        state['H'] = base_h
        state['L'] = base_l

        # CPC $1BBC calls $1FB8 with A=height before bytecodes start.
        # $1A40 clears $1FDE to 0; $1FB8 updates if height != $FF.
        if height != 0xFF:
            half_h = (height & 0xFF) >> 1
            state['proj_E'] = (half_h + base_h + base_l - 15) & 0xFF
            state['proj_D'] = (16 + half_h + base_h - base_l) & 0xFF

        tiles = []
        try:
            self._execute(state, tiles, depth=0)
        except SimulationError as e:
            return tiles, str(e)

        return tiles, None


def generate_assembly(type_results):
    """Generate src/object_types.s assembly include from simulation results.

    type_results: dict {type_idx: (tiles_list, error_msg)}
    tiles_list items are (dH, dL, tile_index)

    Output format:
      obj_type_offsets: word table, one entry per type (indexed by type_byte/2)
                        each = byte offset from obj_type_data to that type's entry
      obj_type_data:    variable-length entries
                        dc.b num_sub_tiles, then dc.b dH,dL,tile for each
    """
    num_types = (MAX_TYPE + 2) // 2
    lines = []
    lines.append("; ============================================================")
    lines.append("; object_types.s - Object type rendering data")
    lines.append("; Generated by simulate_renderer.py - DO NOT EDIT")
    lines.append(";")
    lines.append("; obj_type_offsets: word offset table (indexed by type_byte/2)")
    lines.append("; obj_type_data:   variable-length entries")
    lines.append(";   Each entry: dc.b num_sub_tiles")
    lines.append(";     Followed by: dc.b dH, dL, tile_index  (per sub-tile)")
    lines.append(";   dH/dL are SIGNED byte offsets from object grid position")
    lines.append("; ============================================================")
    lines.append("")

    # First pass: compute byte offsets for each type entry
    offsets = []
    byte_pos = 0
    for i in range(0, MAX_TYPE + 2, 2):
        offsets.append(byte_pos)
        tiles, err = type_results.get(i, ([], None))
        byte_pos += 1  # num_sub_tiles byte
        byte_pos += len(tiles) * 3  # 3 bytes per sub-tile

    # Generate offset table
    lines.append(f"OBJ_TYPE_COUNT equ {num_types}")
    lines.append("")
    lines.append("obj_type_offsets:")
    for idx in range(0, len(offsets), 8):
        chunk = offsets[idx:idx+8]
        vals = ",".join(str(o) for o in chunk)
        lines.append(f"        dc.w    {vals}")
    lines.append("")

    # Generate data
    lines.append("obj_type_data:")
    for i in range(0, MAX_TYPE + 2, 2):
        tiles, err = type_results.get(i, ([], None))
        if tiles:
            lines.append(f"; type ${i:02X} ({len(tiles)} sub-tiles)")
            lines.append(f"        dc.b    {len(tiles)}")
            for dh, dl, tile in tiles:
                dh_s = dh if dh >= 0 else dh + 256
                dl_s = dl if dl >= 0 else dl + 256
                lines.append(
                    f"        dc.b    {dh_s},{dl_s},{tile}"
                    f"  ; dH={dh:+d} dL={dl:+d} tile={tile}")
        else:
            reason = ""
            if err:
                reason = f" ({err})"
            lines.append(f"; type ${i:02X} (unused{reason})")
            lines.append(f"        dc.b    0")

    lines.append("")
    lines.append("        even")
    lines.append("")

    return "\n".join(lines)


def main():
    bin_path = os.path.join(DATA_DIR, "ABADIA1.BIN")
    if not os.path.exists(bin_path):
        print(f"Error: {bin_path} not found", file=sys.stderr)
        sys.exit(1)

    with open(bin_path, "rb") as f:
        data = f.read()

    print(f"ABADIA1.BIN: {len(data)} bytes "
          f"(CPC ${ABADIA1_LOAD:04X}-${ABADIA1_LOAD + len(data) - 1:04X})")

    sim = BytecodeSimulator(data)

    type_results = {}
    succeeded = 0
    failed = 0
    total_tiles = 0
    errors = []

    print(f"\nSimulating {(MAX_TYPE + 2) // 2} object types...\n")

    for type_idx in range(0, MAX_TYPE + 2, 2):
        print(f"--- Type ${type_idx:02X} ---")

        tiles, err = sim.simulate_type(type_idx)
        type_results[type_idx] = (tiles, err)

        if err:
            if tiles:
                print(f"  Partial result ({len(tiles)} tiles before error): {err}")
                failed += 1
                errors.append((type_idx, err))
            else:
                print(f"  Failed: {err}")
                failed += 1
                errors.append((type_idx, err))
        elif len(tiles) == 0:
            print(f"  No tiles drawn (empty type)")
        else:
            succeeded += 1
            total_tiles += len(tiles)
            print(f"  {len(tiles)} tiles:")
            for dh, dl, tile in tiles:
                print(f"    dH={dh:+d} dL={dl:+d} tile={tile}")

    # Generate assembly output
    asm = generate_assembly(type_results)
    out_path = os.path.join(SRC_DIR, "object_types.s")
    with open(out_path, "w", newline="\n") as f:
        f.write(asm)
    print(f"\nAssembly output: {out_path}")

    # Summary
    types_with_tiles = sum(
        1 for tiles, _ in type_results.values() if tiles)
    total_types = (MAX_TYPE + 2) // 2

    print(f"\n{'=' * 60}")
    print(f"SUMMARY")
    print(f"{'=' * 60}")
    print(f"Total types examined:    {total_types}")
    print(f"Types producing tiles:   {types_with_tiles}")
    print(f"Types failed simulation: {failed}")
    print(f"Total tiles drawn:       {total_tiles}")
    if types_with_tiles > 0:
        print(f"Average tiles per type:  {total_tiles / types_with_tiles:.1f}")
    print()

    if errors:
        print("Failed types:")
        for type_idx, err in errors:
            tiles, _ = type_results[type_idx]
            tile_note = f" ({len(tiles)} partial tiles)" if tiles else ""
            print(f"  Type ${type_idx:02X}: {err}{tile_note}")
        print()


if __name__ == "__main__":
    main()
