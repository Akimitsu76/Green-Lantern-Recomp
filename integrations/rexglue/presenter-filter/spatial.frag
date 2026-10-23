// Original bounded spatial reconstruction. No temporal history or game assets.
#version 450
layout(set=0,binding=0) uniform texture2D source_image;
layout(set=0,binding=1) uniform sampler source_sampler;
layout(push_constant) uniform Paint { layout(offset=16) ivec2 output_origin; layout(offset=24) vec2 output_inverse_size; } paint;
layout(location=0) out vec4 color;
float cubic(float x) {
  x=abs(x);
  if(x<1.0) return (1.5*x-2.5)*x*x+1.0;
  if(x<2.0) return ((-0.5*x+2.5)*x-4.0)*x+2.0;
  return 0.0;
}
vec3 read_pixel(ivec2 p,ivec2 dimensions) {
  return texelFetch(sampler2D(source_image,source_sampler),clamp(p,ivec2(0),dimensions-1),0).rgb;
}
void main() {
  vec2 uv=(vec2(ivec2(gl_FragCoord.xy)-paint.output_origin)+0.5)*paint.output_inverse_size;
  ivec2 size=textureSize(sampler2D(source_image,source_sampler),0);
  vec2 pos=uv*vec2(size)-0.5;
  ivec2 base=ivec2(floor(pos)); vec2 f=fract(pos);
  vec3 sum=vec3(0.0); float weights=0.0;
  for(int y=-1;y<=2;++y) for(int x=-1;x<=2;++x) {
    float w=cubic(float(x)-f.x)*cubic(float(y)-f.y);
    sum+=read_pixel(base+ivec2(x,y),size)*w; weights+=w;
  }
  vec3 a=read_pixel(base,size),b=read_pixel(base+ivec2(1,0),size);
  vec3 c=read_pixel(base+ivec2(0,1),size),d=read_pixel(base+ivec2(1,1),size);
  vec3 lo=min(min(a,b),min(c,d)),hi=max(max(a,b),max(c,d));
  vec3 result=clamp(sum/weights,lo,hi); // suppress cubic ringing/halos
#ifdef ASTER_SHARP
  vec3 linear=mix(mix(a,b,f.x),mix(c,d,f.x),f.y);
  result=clamp(result+0.25*(result-linear),lo,hi);
#endif
#ifdef ASTER_DITHER
  // Stable screen-space 4x4 Bayer noise, bounded to half an 8-bit step.
  const int bayer[16]=int[16](0,8,2,10,12,4,14,6,3,11,1,9,15,7,13,5);
  ivec2 q=ivec2(gl_FragCoord.xy)&3;
  result+=(float(bayer[q.y*4+q.x])/16.0-0.46875)/255.0;
#endif
  color=vec4(clamp(result,0.0,1.0),1.0);
}
