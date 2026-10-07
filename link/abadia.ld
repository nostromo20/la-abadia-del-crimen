/* abadia.ld -- links the hybrid QL image at address 0.
 * The image is loaded at an unknown RESPR address; qlstart.s relocates it using the table
 * tools/mkimage.py extracts from the --emit-relocs output. BSS is not in the file: the BASIC
 * loader reserves image + BSS (see boot_h_bas). */
OUTPUT_FORMAT("elf32-m68k")
ENTRY(_start)

SECTIONS
{
	. = 0;
	.text : {
		KEEP(*(.text.start))
		*(.text .text.*)
	}
	.rodata : {
		*(.rodata .rodata.*)
	}
	. = ALIGN(4);
	.init_array : {
		__init_array_start = .;
		KEEP(*(SORT_BY_INIT_PRIORITY(.init_array.*)))
		KEEP(*(.init_array .ctors .ctors.*))
		__init_array_end = .;
	}
	.data : {
		*(.data .data.*)
		. = ALIGN(4);
		__image_end = .;
	}
	.bss (NOLOAD) : {
		__bss_start = .;
		*(.bss .bss.*)
		*(COMMON)
		. = ALIGN(4);
		__bss_end = .;
	}
	/DISCARD/ : {
		*(.comment) *(.note*) *(.eh_frame*) *(.gcc_except_table*) *(.fini_array*) *(.dtors*)
	}
}
