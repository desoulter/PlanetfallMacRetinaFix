#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
struct { char magic[8]; uint32_t width,height; uint64_t interval; } pf_config;
uint64_t pf_present_state;
static uint64_t now_ns=1000000000, present_work;
static int clocks,sleeps,presents,clock_fail,interrupt_sleep,oversleep_us;
int pf_clock_gettime(int clock,struct timespec *t){assert(clock==6);clocks++;if(clock_fail)return -1;t->tv_sec=now_ns/1000000000;t->tv_nsec=now_ns%1000000000;return 0;}
int pf_usleep(unsigned usec){assert(usec>0&&usec<=500000);sleeps++;if(interrupt_sleep){interrupt_sleep=0;now_ns+=1000;return -1;}now_ns+=((uint64_t)usec+oversleep_us)*1000;return 0;}
int pf_vk_present(void *queue,const void *info){assert(queue==(void *)0x1234&&info==(void *)0x5678);presents++;now_ns+=present_work;return -1000001004;}
extern int pf_present(void *,const void *);
void *pf_window=(void *)1;
unsigned char pf_fullscreen=1;
unsigned char app[0xb708];void *pf_application=app;
static unsigned char queued[56];static int pw=1512,ph=945,dw=3024,dh=1890,polled=1;
int pf_sdl_poll_event(void *p){if(p)memcpy(p,queued,56);return polled;}
void pf_sdl_window_size(void *p,int *w,int *h){(void)p;*w=pw;*h=ph;}
void pf_sdl_drawable_size(void *p,int *w,int *h){(void)p;*w=dw;*h=dh;}
extern int pf_pixel_events(void *);
static void put(unsigned char *e,int o,int x){memcpy(e+o,&x,4);}
static int get(unsigned char *e,int o){int x;memcpy(&x,e+o,4);return x;}
static void frame(int w,int h){put(app,0xb688,w);put(app,0xb68c,h);}
static void event(int t,int reason,int a,int b){memset(queued,0,sizeof queued);put(queued,0,t);queued[12]=reason;put(queued,16,a);put(queued,20,b);}
int main(void){unsigned char e[56],orig[56];
 frame(pw,ph);
 event(0x200,5,1512,945);assert(pf_pixel_events(e)==1);assert(get(e,16)==3024&&get(e,20)==1890);
 event(0x200,6,1512,945);memcpy(orig,queued,56);assert(pf_pixel_events(e)==1);assert(!memcmp(e,orig,56));
 pf_config.width=2048;pf_config.height=1280;event(0x200,5,1280,720);pf_pixel_events(e);assert(get(e,16)==2048&&get(e,20)==1280);
 event(0x200,6,1512,945);memcpy(orig,queued,56);pf_pixel_events(e);assert(!memcmp(e,orig,56));pf_config.width=pf_config.height=0;
 pf_fullscreen=0;event(0x200,5,1512,945);memcpy(orig,queued,56);pf_pixel_events(e);assert(!memcmp(e,orig,56));pf_fullscreen=1;
 // Retina output alone must not double mouse coordinates when the UI stays small.
 event(0x400,0,0,125);put(queued,24,200);memcpy(orig,queued,56);pf_pixel_events(e);assert(!memcmp(e,orig,56));
 frame(dw,dh);
 for(int t=0x400;t<=0x402;t++){event(t,0,13,125);put(queued,24,200);put(queued,28,-3);put(queued,32,7);pf_pixel_events(e);
  assert(get(e,16)==13&&get(e,20)==250&&get(e,24)==400);assert(get(e,28)==(t==0x400?-6:-3));assert(get(e,32)==(t==0x400?14:7));}
 event(0x400,0,0,-10);put(queued,24,-15);pf_pixel_events(e);assert(get(e,20)==-20&&get(e,24)==-30);
 for(int t=0x300;t<=0x303;t++){event(t,0,13,25);memcpy(orig,queued,56);pf_pixel_events(e);assert(!memcmp(e,orig,56));}
 event(0x403,0,2,-3);memcpy(orig,queued,56);pf_pixel_events(e);assert(!memcmp(e,orig,56));
 pw=0;event(0x400,0,0,125);memcpy(orig,queued,56);pf_pixel_events(e);assert(!memcmp(e,orig,56));pw=1512;
 frame(pw,ph);event(0x400,0,0,125);put(queued,24,200);memcpy(orig,queued,56);pf_pixel_events(e);assert(!memcmp(e,orig,56));
 pw=100;ph=100;frame(150,125);event(0x400,0,0,11);put(queued,24,13);pf_pixel_events(e);assert(get(e,20)==16&&get(e,24)==16);
 pf_application=NULL;event(0x400,0,0,125);memcpy(orig,queued,56);pf_pixel_events(e);assert(!memcmp(e,orig,56));pf_application=app;
 polled=0;event(0x200,5,100,100);pf_pixel_events(e);assert(get(e,16)==100&&get(e,20)==100);
 assert(pf_pixel_events(NULL)==0);
 assert(pf_present((void *)0x1234,(void *)0x5678)==-1000001004);assert(presents==1&&clocks==0&&sleeps==0);
 pf_config.interval=16666667;present_work=4000000;
 assert(pf_present((void *)0x1234,(void *)0x5678)==-1000001004);assert(pf_present_state==1000000000&&sleeps==0);
 now_ns+=5000000;uint64_t previous=pf_present_state;
 pf_present((void *)0x1234,(void *)0x5678);assert(pf_present_state-previous>=pf_config.interval&&pf_present_state-previous<pf_config.interval+1000);assert(sleeps==1);
 int prior_sleeps=sleeps;now_ns+=500000000;pf_present((void *)0x1234,(void *)0x5678);assert(sleeps==prior_sleeps);
 now_ns=5000;pf_present((void *)0x1234,(void *)0x5678);assert(pf_present_state==5000);
 interrupt_sleep=1;present_work=0;previous=pf_present_state;prior_sleeps=sleeps;
 pf_present((void *)0x1234,(void *)0x5678);assert(sleeps==prior_sleeps+2&&pf_present_state-previous>=pf_config.interval);
 clock_fail=1;prior_sleeps=sleeps;assert(pf_present((void *)0x1234,(void *)0x5678)==-1000001004);assert(sleeps==prior_sleeps);clock_fail=0;
 pf_config.interval=1000000000;previous=pf_present_state;prior_sleeps=sleeps;
 pf_present((void *)0x1234,(void *)0x5678);assert(sleeps==prior_sleeps+2&&pf_present_state-previous>=1000000000);
 pf_present_state=0;now_ns=1000000000;oversleep_us=2000;pf_config.interval=16666667;
 pf_present((void *)0x1234,(void *)0x5678);previous=now_ns;
 for(int i=0;i<300;i++){now_ns+=1000000;pf_present((void *)0x1234,(void *)0x5678);}
 assert(now_ns-previous>=300*pf_config.interval&&now_ns-previous<300*pf_config.interval+2100000);
 puts("PASS: Retina/custom resize, windowed/event passthrough, actual-UI mouse mapping, fractional/negative coordinates, null/no-event handling");
 puts("PASS: cap disabled, pacing with present/render cost, wake-up jitter without drift, sleep interruption, pause/backwards clock, clock failure, long intervals, Vulkan return/argument preservation");return 0;
}
