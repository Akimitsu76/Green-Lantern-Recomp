// Unlink only an arena exclusively created by this call. The open descriptor
// remains valid; the kernel releases the anonymous object after its last use.
#include <dlfcn.h>
#include <fcntl.h>
#include <sys/mman.h>
#include <cstring>
#include <cerrno>
extern "C" int shm_open(const char* name, int flags, mode_t mode) {
  using Open = int (*)(const char*,int,mode_t);
  static auto original = reinterpret_cast<Open>(dlsym(RTLD_NEXT,"shm_open"));
  if(!original) { errno=ENOSYS; return -1; }
  bool arena=name && std::strncmp(name,"/xenia_memory_",14)==0 && (flags&O_CREAT);
  int fd=original(name,arena ? flags|O_EXCL : flags,mode);
  if(arena && fd>=0) { int saved=errno; shm_unlink(name); errno=saved; }
  return fd;
}
