// Optional native diagnostics. Hooks forward every call without changing it.
#import <AppKit/AppKit.h>
#import <QuartzCore/CAMetalLayer.h>
#include <dlfcn.h>
#include <mach-o/dyld.h>
#include <pthread.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

typedef void *PFHandle;
typedef struct { uint32_t w,h; } Extent;
typedef struct { uint32_t minCount,maxCount; Extent current,min,max; uint32_t rest[5]; } Caps;
typedef struct { uint32_t type; const void *next; uint32_t flags; PFHandle surface;
 uint32_t minImages,format,colorSpace; Extent extent; uint32_t layers,usage,sharing,queueCount;
 const uint32_t *queues; uint32_t transform,alpha,presentMode,clipped; PFHandle old; } SwapInfo;
typedef struct { uint32_t type; const void *next; uint32_t flags,imageType,format,w,h,d;
 uint32_t mips,layers,samples,tiling,usage,sharing,queueCount; const uint32_t *queues;
 uint32_t initialLayout; } ImageInfo;
typedef struct { float x,y,w,h,minDepth,maxDepth; } Viewport;
typedef struct { uint32_t flags; void *format; int w,h; } SurfaceHead;
_Static_assert(sizeof(Caps)==52,"Vulkan surface capabilities ABI");
_Static_assert(__builtin_offsetof(SwapInfo,extent)==44,"Vulkan swapchain ABI");
_Static_assert(__builtin_offsetof(ImageInfo,usage)==56,"Vulkan image ABI");

extern void *SDL_CreateWindow(const char *,int,int,int,int,uint32_t);
extern int SDL_PollEvent(void *);
extern void SDL_GetWindowSize(void *,int *,int *);
extern void SDL_SetWindowSize(void *,int,int);
extern void SDL_GL_GetDrawableSize(void *,int *,int *);
extern void SDL_Vulkan_GetDrawableSize(void *,int *,int *);
extern uint32_t SDL_GetWindowFlags(void *);
extern int SDL_SetWindowFullscreen(void *,uint32_t);
extern int SDL_Vulkan_CreateSurface(void *,PFHandle,PFHandle *);
extern void *SDL_CreateColorCursor(void *,int,int);
extern void SDL_SetCursor(void *);
extern int32_t vkGetPhysicalDeviceSurfaceCapabilitiesKHR(PFHandle,PFHandle,Caps *);
extern int32_t vkCreateSwapchainKHR(PFHandle,const SwapInfo *,const void *,PFHandle *);
extern int32_t vkCreateImage(PFHandle,const ImageInfo *,const void *,PFHandle *);
extern void vkCmdSetViewport(PFHandle,uint32_t,uint32_t,const Viewport *);
extern int32_t vkQueuePresentKHR(PFHandle,const void *);

static FILE *output;
static pthread_mutex_t logLock=PTHREAD_MUTEX_INITIALIZER;
static pthread_mutex_t seenLock=PTHREAD_MUTEX_INITIALIZER;
static pthread_mutex_t fpsLock=PTHREAD_MUTEX_INITIALIZER;
static double started;
static uintptr_t gameImage;
static double now(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec+t.tv_nsec/1e9;}
static void trace(const char *fmt,...) {
 if(!output)return;
 pthread_mutex_lock(&logLock);
 fprintf(output,"[%.3f] ",now()-started);
 va_list ap;va_start(ap,fmt);vfprintf(output,fmt,ap);va_end(ap);fputc('\n',output);fflush(output);
 pthread_mutex_unlock(&logLock);
}
static int onceSize(unsigned tag,uint32_t w,uint32_t h) {
 static uint64_t seen[3][128];static unsigned counts[3];
 uint64_t key=((uint64_t)w<<32)|h;int yes=0;
 pthread_mutex_lock(&seenLock);
 for(unsigned i=0;i<counts[tag];i++)if(seen[tag][i]==key)goto done;
 if(counts[tag]<128){seen[tag][counts[tag]++]=key;yes=1;}
done:pthread_mutex_unlock(&seenLock);return yes;
}
static void views(NSView *view,unsigned depth) {
 if(depth>5)return;
 CALayer *layer=view.layer;
 if([layer isKindOfClass:CAMetalLayer.class]) {
  CAMetalLayer *metal=(CAMetalLayer *)layer;NSSize backing=[view convertSizeToBacking:view.bounds.size];
  trace("METAL view=%s bounds=%.0fx%.0f backing=%.0fx%.0f contentsScale=%.3f drawable=%.0fx%.0f displaySync=%d",
   NSStringFromClass(view.class).UTF8String,view.bounds.size.width,view.bounds.size.height,
   backing.width,backing.height,metal.contentsScale,metal.drawableSize.width,metal.drawableSize.height,metal.displaySyncEnabled);
 }
 for(NSView *child in view.subviews)views(child,depth+1);
}
static void windowState(void *w,const char *reason,int hasSurface) {
 if(!w)return;int a=0,b=0,c=0,d=0;SDL_GetWindowSize(w,&a,&b);
 if(hasSurface)SDL_Vulkan_GetDrawableSize(w,&c,&d);
 trace("WINDOW %s flags=0x%x points=%dx%d vulkanDrawable=%dx%d",reason,SDL_GetWindowFlags(w),a,b,c,d);
 if(!NSThread.isMainThread)return;
 for(NSWindow *window in NSApp.windows)if([NSStringFromClass(window.class) containsString:@"SDL"]) {
  NSScreen *screen=window.screen;
  trace("COCOA frame=%.0fx%.0f backingScale=%.3f screen=%.0fx%.0f screenScale=%.3f",window.frame.size.width,
   window.frame.size.height,window.backingScaleFactor,screen.frame.size.width,screen.frame.size.height,screen.backingScaleFactor);
  if(screen){CGDirectDisplayID display=[screen.deviceDescription[@"NSScreenNumber"] unsignedIntValue];
   CGDisplayModeRef mode=CGDisplayCopyDisplayMode(display);
   if(mode){trace("DISPLAY id=%u mode=%zux%zu pixels=%zux%zu reportedModeHz=%.3f",display,
    CGDisplayModeGetWidth(mode),CGDisplayModeGetHeight(mode),CGDisplayModeGetPixelWidth(mode),
    CGDisplayModeGetPixelHeight(mode),CGDisplayModeGetRefreshRate(mode));CGDisplayModeRelease(mode);}}
  views(window.contentView,0);
 }
}
static void *traceCreateWindow(const char *title,int x,int y,int w,int h,uint32_t flags) {
 void *win=SDL_CreateWindow(title,x,y,w,h,flags);
 trace("SDL_CreateWindow request=%dx%d flags=0x%x result=%p",w,h,flags,win);windowState(win,"created",0);return win;
}
static void appState(void) {
 if(!gameImage)return;
 uintptr_t app=*(uintptr_t *)(gameImage+0x15aed28);
 if(!app)return;
 int *client=(int *)(gameImage+0x15aed80);
 trace("APP resize=%dx%d uiFrame=%dx%d uiBasis=%dx%d client=%dx%d fullscreen=%u",
  *(int *)(app+0xb638),*(int *)(app+0xb63c),*(int *)(app+0xb688),*(int *)(app+0xb68c),
  *(int *)(app+0xb690),*(int *)(app+0xb694),client[0],client[1],*(unsigned char *)(gameImage+0x15aed9c));
}
static int tracePoll(void *event) {
 int result=SDL_PollEvent(event);
 if(result&&event){uint32_t type;memcpy(&type,event,4);
  unsigned char *bytes=event;
  if(type==0x200&&(bytes[12]==5||bytes[12]==6)){
   int a,b;memcpy(&a,bytes+16,4);memcpy(&b,bytes+20,4);
   trace("SDL_WINDOW_EVENT before-conversion kind=%u size=%dx%d pollCaller=%p",bytes[12],a,b,__builtin_return_address(0));appState();
  }}
 return result;
}
static void traceWindowSize(void *w,int *a,int *b) {
 SDL_GetWindowSize(w,a,b);static unsigned count;
 if(__atomic_fetch_add(&count,1,__ATOMIC_RELAXED)<24)trace("SDL_GetWindowSize result=%dx%d caller=%p",a?*a:-1,b?*b:-1,__builtin_return_address(0));
}
static void traceSetSize(void *w,int a,int b) {
 SDL_SetWindowSize(w,a,b);static unsigned count;
 if(__atomic_fetch_add(&count,1,__ATOMIC_RELAXED)<24)trace("SDL_SetWindowSize request=%dx%d",a,b);
}
static void traceGLSize(void *w,int *a,int *b) {
 SDL_GL_GetDrawableSize(w,a,b);static unsigned count;
 if(__atomic_fetch_add(&count,1,__ATOMIC_RELAXED)<24)trace("SDL_GL_GetDrawableSize result=%dx%d caller=%p",a?*a:-1,b?*b:-1,__builtin_return_address(0));
}
static int traceFullscreen(void *w,uint32_t flags) {
 trace("SDL_SetWindowFullscreen request=0x%x",flags);int result=SDL_SetWindowFullscreen(w,flags);
 trace("SDL_SetWindowFullscreen result=%d",result);windowState(w,"fullscreen",0);return result;
}
static int traceSurface(void *w,PFHandle instance,PFHandle *surface) {
 int result=SDL_Vulkan_CreateSurface(w,instance,surface);trace("SDL_Vulkan_CreateSurface result=%d",result);
 windowState(w,"surface-created",result);return result;
}
static void *traceCursor(void *surface,int x,int y) {
 void *cursor=SDL_CreateColorCursor(surface,x,y);SurfaceHead *s=surface;
 trace("SDL_CreateColorCursor image=%dx%d result=%p",s?s->w:0,s?s->h:0,cursor);return cursor;
}
static void traceSetCursor(void *cursor) {
 SDL_SetCursor(cursor);static unsigned count;
 if(__atomic_fetch_add(&count,1,__ATOMIC_RELAXED)<16)trace("SDL_SetCursor cursor=%p",cursor);
}
static int32_t traceCaps(PFHandle device,PFHandle surface,Caps *caps) {
 int32_t result=vkGetPhysicalDeviceSurfaceCapabilitiesKHR(device,surface,caps);
 if(!result&&caps&&onceSize(0,caps->current.w,caps->current.h))trace("VULKAN surface current=%ux%u min=%ux%u max=%ux%u",
  caps->current.w,caps->current.h,caps->min.w,caps->min.h,caps->max.w,caps->max.h);
 return result;
}
static int32_t traceSwapchain(PFHandle device,const SwapInfo *info,const void *allocator,PFHandle *swapchain) {
 int32_t result=vkCreateSwapchainKHR(device,info,allocator,swapchain);
 if(info)trace("SWAPCHAIN extent=%ux%u presentMode=%u imageCount=%u result=%d",info->extent.w,info->extent.h,info->presentMode,info->minImages,result);
 return result;
}
static int32_t traceImage(PFHandle device,const ImageInfo *info,const void *allocator,PFHandle *image) {
 int32_t result=vkCreateImage(device,info,allocator,image);
 if(info&&(info->usage&0x30)&&(info->w>=700||info->h>=500)&&onceSize(1,info->w,info->h))
  trace("ATTACHMENT image=%ux%u depth=%u usage=0x%x samples=%u result=%d",info->w,info->h,info->d,info->usage,info->samples,result);
 return result;
}
static void traceViewport(PFHandle command,uint32_t first,uint32_t count,const Viewport *vp) {
 vkCmdSetViewport(command,first,count,vp);
 if(vp&&count){uint32_t w=(uint32_t)__builtin_fabsf(vp->w),h=(uint32_t)__builtin_fabsf(vp->h);
  if((w>=700||h>=500)&&onceSize(2,w,h)){trace("VIEWPORT width=%.1f height=%.1f origin=%.1f,%.1f",vp->w,vp->h,vp->x,vp->y);appState();}}
}
static int32_t tracePresent(PFHandle queue,const void *info) {
 int32_t result=vkQueuePresentKHR(queue,info);static double since;static unsigned frames;
 double t=now(),elapsed=0,rate=0;pthread_mutex_lock(&fpsLock);
 if(!since)since=t;
 ++frames;if(t-since>=3){elapsed=t-since;rate=frames/elapsed;frames=0;since=t;}
 pthread_mutex_unlock(&fpsLock);
 if(elapsed)trace("PRESENT submissionsPerSecond=%.2f interval=%.2f lastResult=%d",rate,elapsed,result);
 return result;
}
#define INTERPOSE(replacement, original) \
 __attribute__((used)) static struct {const void *replace;const void *target;} pair_##original \
 __attribute__((section("__DATA,__interpose")))={(const void *)&replacement,(const void *)&original};
INTERPOSE(traceCreateWindow,SDL_CreateWindow)
INTERPOSE(tracePoll,SDL_PollEvent)
INTERPOSE(traceWindowSize,SDL_GetWindowSize)
INTERPOSE(traceSetSize,SDL_SetWindowSize)
INTERPOSE(traceGLSize,SDL_GL_GetDrawableSize)
INTERPOSE(traceFullscreen,SDL_SetWindowFullscreen)
INTERPOSE(traceSurface,SDL_Vulkan_CreateSurface)
INTERPOSE(traceCursor,SDL_CreateColorCursor)
INTERPOSE(traceSetCursor,SDL_SetCursor)
INTERPOSE(traceCaps,vkGetPhysicalDeviceSurfaceCapabilitiesKHR)
INTERPOSE(traceSwapchain,vkCreateSwapchainKHR)
INTERPOSE(traceImage,vkCreateImage)
INTERPOSE(traceViewport,vkCmdSetViewport)
INTERPOSE(tracePresent,vkQueuePresentKHR)
__attribute__((constructor)) static void initialize(void) {
 char executable[4096];uint32_t pathSize=sizeof executable;
 if(!_NSGetExecutablePath(executable,&pathSize)){
  const char *name=strrchr(executable,'/');name=name?name+1:executable;
  if(!strcmp(name,"Age of Wonders - Planetfall"))gameImage=(uintptr_t)_dyld_get_image_header(0);
 }
 const char *path=getenv("PF_DISPLAY_TRACE");char fallback[4096];
 if(!path&&gameImage){Dl_info ownImage;
  if(dladdr((const void *)&initialize,&ownImage)&&ownImage.dli_fname){const char *slash=strrchr(ownImage.dli_fname,'/');
   if(slash){snprintf(fallback,sizeof fallback,"%.*s/game_display_trace.log",(int)(slash-ownImage.dli_fname),ownImage.dli_fname);path=fallback;}}
 }
 if(!path)return;output=fopen(path,"w");started=now();
 trace("Planetfall display trace v1.1.0; observational hooks only; main-image symbols can use ASLR addresses");
 trace("IMAGE mainSlide=0x%llx",(unsigned long long)_dyld_get_image_vmaddr_slide(0));
 if(gameImage){const uint32_t sites[2]={0xec18e4,0xec1ad9};unsigned covered=0;
  for(unsigned i=0;i<2;i++){unsigned char *code=(unsigned char *)(gameImage+sites[i]);int32_t rel;memcpy(&rel,code+1,4);
   if(code[0]==0xe8&&(int64_t)sites[i]+5+rel==0x7000)++covered;}
  trace("PATCH eventPollCoverage=%u/2",covered);
  const unsigned char *config=(const unsigned char *)(gameImage+0x7d00);
  if(!memcmp(config,"PFCONF11",8)){uint32_t w,h;uint64_t interval;
   memcpy(&w,config+8,4);memcpy(&h,config+12,4);memcpy(&interval,config+16,8);
   trace("PATCH configuredRender=%ux%u pacingIntervalNs=%llu",w,h,(unsigned long long)interval);
  }
 }
}
