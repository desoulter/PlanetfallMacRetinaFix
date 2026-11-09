#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
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
 puts("PASS: fullscreen RESIZED, ignored SIZE_CHANGED, windowed passthrough, actual-UI mouse mapping, low-resolution UI regression, fractional/negative coordinates, keyboard/wheel passthrough, null/no-event handling");return 0;
}
