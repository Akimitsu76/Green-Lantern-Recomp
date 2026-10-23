// Aster Vulkan presenter adapter. AMD EASU implementation: see FSR-LICENSE.txt.
#version 450
#extension GL_GOOGLE_include_directive : require
#define A_GPU 1
#define A_GLSL 1
#include "ffx_a.h"
#define FSR_EASU_F 1
layout(set=0,binding=0) uniform texture2D source_image;
layout(set=0,binding=1) uniform sampler source_sampler;
layout(push_constant) uniform Paint {
  layout(offset=16) ivec2 output_origin;
  layout(offset=24) vec2 output_inverse_size;
} paint;
layout(location=0) out vec4 color;
AF4 FsrEasuRF(AF2 p) { return textureGather(sampler2D(source_image,source_sampler),p,0); }
AF4 FsrEasuGF(AF2 p) { return textureGather(sampler2D(source_image,source_sampler),p,1); }
AF4 FsrEasuBF(AF2 p) { return textureGather(sampler2D(source_image,source_sampler),p,2); }
#include "ffx_fsr1.h"
void main() {
  vec2 input_size=vec2(textureSize(sampler2D(source_image,source_sampler),0));
  vec2 output_size=1.0/paint.output_inverse_size;
  ivec2 ip=ivec2(gl_FragCoord.xy)-paint.output_origin;
  vec3 result;
  // EASU targets enlargement up to 2x per axis. Keep neutral bilinear at 1:1,
  // reduction and larger ratios until an intermediate-pass path is available.
  if(all(greaterThanEqual(output_size,input_size)) &&
     all(lessThanEqual(output_size,2.0*input_size)) && any(greaterThan(output_size,input_size))) {
    AU4 c0,c1,c2,c3;
    FsrEasuCon(c0,c1,c2,c3,input_size.x,input_size.y,input_size.x,input_size.y,output_size.x,output_size.y);
    FsrEasuF(result,uvec2(max(ip,ivec2(0))),c0,c1,c2,c3);
  } else {
    result=texture(sampler2D(source_image,source_sampler),(vec2(ip)+0.5)*paint.output_inverse_size).rgb;
  }
#ifdef ASTER_DITHER
  const int bayer[16]=int[16](0,8,2,10,12,4,14,6,3,11,1,9,15,7,13,5);
  ivec2 q=ivec2(gl_FragCoord.xy)&3;
  result+=(float(bayer[q.y*4+q.x])/16.0-0.46875)/255.0;
#endif
  color=vec4(clamp(result,0.0,1.0),1.0);
}
