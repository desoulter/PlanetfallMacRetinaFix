#import <AppKit/AppKit.h>
#import <CoreVideo/CoreVideo.h>
#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

typedef struct { uint32_t format; int w,h,refresh_rate; void *data; } DisplayMode;
typedef struct { uint32_t type; const void *next; uint32_t flags; const void *app;
 uint32_t layerCount; const char *const *layers; uint32_t extCount; const char *const *exts; } InstanceInfo;
typedef struct { uint32_t minCount,maxCount,cw,ch,minw,minh,maxw,maxh,maxLayers,transforms,currentTransform,alpha,usage; } Caps;
#define SYM(lib, name, ret, args) ret (*name) args = (void *)dlsym(lib, #name); if (!name) {fprintf(stderr,"missing %s\n",#name); return 2;}
int main(int argc,char **argv) { @autoreleasepool {
 setbuf(stdout,NULL);
 if(argc!=3) {fprintf(stderr,"usage: probe SDL-path MoltenVK-path\n");return 2;}
 void *s=dlopen(argv[1],RTLD_NOW|RTLD_LOCAL); if(!s){puts(dlerror());return 2;}
 void *v=dlopen(argv[2],RTLD_NOW|RTLD_LOCAL); if(!v){puts(dlerror());return 2;}
 SYM(s,SDL_Init,int,(uint32_t)); SYM(s,SDL_Quit,void,(void));
 SYM(s,SDL_GetError,const char *,(void)); SYM(s,SDL_GetVersion,void,(unsigned char *));
 SYM(s,SDL_GetNumVideoDisplays,int,(void)); SYM(s,SDL_GetCurrentDisplayMode,int,(int,DisplayMode *));
 SYM(s,SDL_GetDisplayName,const char *,(int)); SYM(s,SDL_Vulkan_LoadLibrary,int,(const char *));
 SYM(s,SDL_CreateWindow,void *,(const char *,int,int,int,int,uint32_t));
 SYM(s,SDL_DestroyWindow,void,(void *)); SYM(s,SDL_GetWindowSize,void,(void *,int *,int *));
 SYM(s,SDL_Vulkan_GetDrawableSize,void,(void *,int *,int *));
 SYM(s,SDL_Vulkan_GetInstanceExtensions,int,(void *,uint32_t *,const char **));
 SYM(s,SDL_Vulkan_CreateSurface,int,(void *,void *,void **));
 SYM(v,vkCreateInstance,int,(const InstanceInfo *,const void *,void **));
 SYM(v,vkEnumeratePhysicalDevices,int,(void *,uint32_t *,void **));
 SYM(v,vkGetPhysicalDeviceSurfaceCapabilitiesKHR,int,(void *,void *,Caps *));
 SYM(v,vkGetPhysicalDeviceSurfacePresentModesKHR,int,(void *,void *,uint32_t *,uint32_t *));
 SYM(v,vkDestroySurfaceKHR,void,(void *,void *,void *));
 SYM(v,vkDestroyInstance,void,(void *,void *));
 unsigned char ver[3]; SDL_GetVersion(ver);printf("SDL=%u.%u.%u\n",ver[0],ver[1],ver[2]);
 if(SDL_Init(0x20)){printf("SDL_Init failed: %s\n",SDL_GetError());return 3;}
 int count=SDL_GetNumVideoDisplays();printf("displays=%d\n",count);
 for(int i=0;i<count;i++){DisplayMode m={0};int rc=SDL_GetCurrentDisplayMode(i,&m);
  printf("display[%d]=%s rc=%d mode=%dx%d reported_hz=%d\n",i,SDL_GetDisplayName(i),rc,m.w,m.h,m.refresh_rate);}
 for(NSScreen *screen in NSScreen.screens){CGDirectDisplayID did=[screen.deviceDescription[@"NSScreenNumber"] unsignedIntValue];
  CGDisplayModeRef m=CGDisplayCopyDisplayMode(did); CVDisplayLinkRef link=NULL; double nominal=0;
  if(CVDisplayLinkCreateWithCGDisplay(did,&link)==kCVReturnSuccess){CVTime t=CVDisplayLinkGetNominalOutputVideoRefreshPeriod(link);if(t.timeValue>0 && !(t.flags&kCVTimeIsIndefinite))nominal=(double)t.timeScale/t.timeValue;CVDisplayLinkRelease(link);}
  printf("CG display=%u screen=%.0fx%.0f scale=%.2f mode=%zux%zu pixels=%zux%zu mode_hz=%.3f nominal_link_hz=%.3f\n",did,screen.frame.size.width,screen.frame.size.height,screen.backingScaleFactor,CGDisplayModeGetWidth(m),CGDisplayModeGetHeight(m),CGDisplayModeGetPixelWidth(m),CGDisplayModeGetPixelHeight(m),CGDisplayModeGetRefreshRate(m),nominal);if(m)CGDisplayModeRelease(m);}
 if(SDL_Vulkan_LoadLibrary(argv[2])){printf("Vulkan load failed: %s\n",SDL_GetError());SDL_Quit();return 3;}
 for(int hi=0;hi<2;hi++){
  uint32_t flags=0x10000008u|(hi?0x2000u:0);
  void *w=SDL_CreateWindow("Planetfall hidden display probe",0x2fff0000,0x2fff0000,1280,720,flags);
  if(!w){printf("CreateWindow hi=%d failed: %s\n",hi,SDL_GetError());continue;}
  uint32_t extn=0;const char *exts[8]={0};SDL_Vulkan_GetInstanceExtensions(w,&extn,NULL);if(extn>8)return 4;
  SDL_Vulkan_GetInstanceExtensions(w,&extn,exts);
  InstanceInfo ci={.type=1,.extCount=extn,.exts=exts};void *instance=NULL;int rc=vkCreateInstance(&ci,NULL,&instance);
  if(rc){printf("vkCreateInstance=%d\n",rc);SDL_DestroyWindow(w);continue;}
  void *surface=NULL;int ok=SDL_Vulkan_CreateSurface(w,instance,&surface);int a=0,b=0,c=0,d=0;
  SDL_GetWindowSize(w,&a,&b);SDL_Vulkan_GetDrawableSize(w,&c,&d);
  printf("highdpi=%d flags=0x%x window=%dx%d drawable=%dx%d surface_ok=%d\n",hi,flags,a,b,c,d,ok);
  if(ok){uint32_t n=8;void *physical[8]={0};rc=vkEnumeratePhysicalDevices(instance,&n,physical);
   if(!rc && n){Caps cap={0};rc=vkGetPhysicalDeviceSurfaceCapabilitiesKHR(physical[0],surface,&cap);
    printf("  capabilities_rc=%d currentExtent=%ux%u min=%ux%u max=%ux%u\n",rc,cap.cw,cap.ch,cap.minw,cap.minh,cap.maxw,cap.maxh);
    uint32_t pn=16,modes[16]={0};rc=vkGetPhysicalDeviceSurfacePresentModesKHR(physical[0],surface,&pn,modes);printf("  present_modes rc=%d:",rc);for(uint32_t i=0;i<pn&&i<16;i++)printf(" %u",modes[i]);puts("");}
   vkDestroySurfaceKHR(instance,surface,NULL);}
  vkDestroyInstance(instance,NULL);SDL_DestroyWindow(w);
 }
 SDL_Quit();return 0;
}}
