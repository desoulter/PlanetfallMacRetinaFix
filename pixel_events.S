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
