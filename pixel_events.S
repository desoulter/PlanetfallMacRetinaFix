// x86_64 SysV wrapper around both of the game's SDL_PollEvent call sites.
// This exact game build processes RESIZED (5) and ignores SIZE_CHANGED (6).
// Convert fullscreen resize dimensions into drawable pixels. Mouse positions
// use the application's actual UI frame, avoiding a fixed Retina assumption.
.text
.globl _pf_pixel_events
_pf_pixel_events:
    pushq %rbp
    movq %rsp, %rbp
    pushq %rbx
    subq $0x38, %rsp
    movq %rdi, %rbx
    callq _pf_sdl_poll_event
    movl %eax, -28(%rbp)
    testl %eax, %eax
    jz Ldone
    testq %rbx, %rbx
    jz Ldone
    movl (%rbx), %eax
    cmpl $0x200, %eax
    jne Lmouse_check
    cmpb $5, 12(%rbx)
    jne Ldone
    movzbl _pf_fullscreen(%rip), %eax
    testb %al, %al
    je Ldone
    jmp Ldimensions
Lmouse_check:
    subl $0x400, %eax
    cmpl $2, %eax
    ja Ldone
Ldimensions:
    movq _pf_window(%rip), %rdi
    testq %rdi, %rdi
    jz Ldone
    leaq -16(%rbp), %rsi
    leaq -12(%rbp), %rdx
    callq _pf_sdl_window_size
    cmpl $0x200, (%rbx)
    je Ldrawable
    // Application fields b688/b68c are the viewport dimensions passed to
    // both Iggy layout and input handling, updated together by the game.
    movq _pf_application(%rip), %rax
    testq %rax, %rax
    jz Ldone
    movl 0xb688(%rax), %ecx
    movl %ecx, -24(%rbp)
    movl 0xb68c(%rax), %ecx
    movl %ecx, -20(%rbp)
    jmp Lvalidate
Ldrawable:
    movl _pf_config+8(%rip), %eax
    movl _pf_config+12(%rip), %ecx
    testl %eax, %eax
    jle Lnative_drawable
    testl %ecx, %ecx
    jle Lnative_drawable
    cmpl $8192, %eax
    jg Lnative_drawable
    cmpl $8192, %ecx
    jg Lnative_drawable
    // A configured resolution is the full render frame, independent of
    // stale logical dimensions carried by queued desktop resize events.
    movl %eax, 16(%rbx)
    movl %ecx, 20(%rbx)
    jmp Ldone
Lnative_drawable:
    movq _pf_window(%rip), %rdi
    leaq -24(%rbp), %rsi
    leaq -20(%rbp), %rdx
    callq _pf_sdl_drawable_size
Lvalidate:
    cmpl $0, -16(%rbp)
    jle Ldone
    cmpl $0, -12(%rbp)
    jle Ldone
    cmpl $0, -24(%rbp)
    jle Ldone
    cmpl $0, -20(%rbp)
    jle Ldone
    cmpl $16384, -24(%rbp)
    jg Ldone
    cmpl $16384, -20(%rbp)
    jg Ldone
    // Converting one field uses a signed 64-bit intermediate, including
    // negative out-of-window mouse coordinates and relative movement.
.macro SCALE field, pixels, points
    movslq \field(%rbx), %rax
    movslq \pixels(%rbp), %rcx
    imulq %rcx, %rax
    cqto
    movslq \points(%rbp), %rcx
    idivq %rcx
    movl %eax, \field(%rbx)
.endm
    cmpl $0x200, (%rbx)
    je Lwindow
    SCALE 20, -24, -16
    SCALE 24, -20, -12
    cmpl $0x400, (%rbx)
    jne Ldone
    SCALE 28, -24, -16
    SCALE 32, -20, -12
    jmp Ldone
Lwindow:
    SCALE 16, -24, -16
    SCALE 20, -20, -12
Ldone:
    movl -28(%rbp), %eax
    addq $0x38, %rsp
    popq %rbx
    popq %rbp
    retq

// Fixed entry offset keeps the patched presentation call independent of
// instruction-size changes in the event wrapper above.
.org 0x400, 0
.globl _pf_present
_pf_present:
    cmpq $0, _pf_config+16(%rip)
    je Lpresent_direct
    pushq %rbp
    movq %rsp, %rbp
    pushq %rbx
    subq $0x38, %rsp
    movq %rdi, -16(%rbp)
    movq %rsi, -24(%rbp)
    movq _pf_config+16(%rip), %rbx
Lclock:
    movl $6, %edi // CLOCK_MONOTONIC on the supported macOS ABI
    leaq -48(%rbp), %rsi
    callq _pf_clock_gettime
    testl %eax, %eax
    jne Lpresent_call
    imulq $1000000000, -48(%rbp), %rax
    addq -40(%rbp), %rax
    movq _pf_present_state(%rip), %rcx
    testq %rcx, %rcx
    je Lready
    cmpq %rcx, %rax
    jb Lready // reset safely if the clock moves backwards
    addq %rbx, %rcx
    cmpq %rcx, %rax
    jae Ldeadline_due
    subq %rax, %rcx
    movq %rcx, %rax
    // Round up to a microsecond and sleep; retry after interruptions.
    // Fixed deadlines absorb normal wake-up jitter without accumulating it.
    addq $999, %rax
    xorl %edx, %edx
    movl $1000, %ecx
    divq %rcx
    movl %eax, %edi
    cmpl $500000, %edi
    jbe Lsleep
    movl $500000, %edi
Lsleep:
    callq _pf_usleep
    jmp Lclock
Ldeadline_due:
    movq %rax, %rdx
    subq %rcx, %rdx
    cmpq %rbx, %rdx
    jae Lready // discard missed deadlines instead of accumulating a backlog
    movq %rcx, %rax
Lready:
    movq %rax, _pf_present_state(%rip)
Lpresent_call:
    movq -16(%rbp), %rdi
    movq -24(%rbp), %rsi
    callq _pf_vk_present
    addq $0x38, %rsp
    popq %rbx
    popq %rbp
    retq
Lpresent_direct:
    jmp _pf_vk_present
