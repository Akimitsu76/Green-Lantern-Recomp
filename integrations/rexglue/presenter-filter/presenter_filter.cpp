// ReXGlue 0.10.0 Linux ABI compatibility module. No guest code or assets.
#include <rex/ui/vulkan/presenter.h>
#include <rex/ui/vulkan/device.h>
#include <dlfcn.h>
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include "cubic_spirv.h"
#include "sharp_spirv.h"
#include "cubic_dither_spirv.h"
#include "sharp_dither_spirv.h"
#include "fsr_easu_spirv.h"
#include "fsr_easu_dither_spirv.h"
namespace rex::ui::vulkan {
VkPipeline VulkanPresenter::CreateGuestOutputPaintPipeline(GuestOutputPaintEffect effect,
                                                         VkRenderPass render_pass) {
  static_assert(sizeof(VulkanPresenter)==1312, "Pinned SDK layout required");
  using Original = VkPipeline (*)(VulkanPresenter*, GuestOutputPaintEffect, VkRenderPass);
  static auto original = reinterpret_cast<Original>(dlsym(RTLD_NEXT,
    "_ZN3rex2ui6vulkan15VulkanPresenter30CreateGuestOutputPaintPipelineENS0_9Presenter22GuestOutputPaintEffectEP14VkRenderPass_T"));
  if (!original) { std::fputs("AsterPresenter: pinned SDK symbol unavailable\n",stderr); return VK_NULL_HANDLE; }
  const char* filter=std::getenv("ASTER_PRESENT_FILTER");
  bool cubic=filter && std::strcmp(filter,"cubic")==0;
  bool sharp=filter && std::strcmp(filter,"sharp")==0;
  bool fsr=filter && std::strcmp(filter,"fsr1")==0;
  bool final_pass=render_pass==paint_context_.swapchain_render_pass;
  VkShaderModule custom=VK_NULL_HANDLE;
  VkShaderModule previous=guest_output_paint_fs_[size_t(effect)];
  const auto& dfn=vulkan_device_->functions(); const auto device=vulkan_device_->device();
  if(final_pass && (effect==GuestOutputPaintEffect::kBilinear || effect==GuestOutputPaintEffect::kBilinearDither) && (cubic||sharp||fsr)) {
    VkShaderModuleCreateInfo info{}; info.sType=VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO;
    bool dither=effect==GuestOutputPaintEffect::kBilinearDither;
    info.codeSize=dither?(sharp?sizeof(sharp_dither_spirv):sizeof(cubic_dither_spirv)):(sharp?sizeof(sharp_spirv):sizeof(cubic_spirv));
    info.pCode=dither?(sharp?sharp_dither_spirv:cubic_dither_spirv):(sharp?sharp_spirv:cubic_spirv);
    if(fsr) {
      info.codeSize=dither?sizeof(fsr_easu_dither_spirv):sizeof(fsr_easu_spirv);
      info.pCode=dither?fsr_easu_dither_spirv:fsr_easu_spirv;
    }
    if(dfn.vkCreateShaderModule(device,&info,nullptr,&custom)==VK_SUCCESS) guest_output_paint_fs_[size_t(effect)]=custom;
    else std::fputs("AsterPresenter: spatial filter unavailable; using bilinear\n",stderr);
  }
  VkPipeline result=original(this,effect,render_pass);
  guest_output_paint_fs_[size_t(effect)]=previous;
  if(custom!=VK_NULL_HANDLE) dfn.vkDestroyShaderModule(device,custom,nullptr);
  if(result!=VK_NULL_HANDLE && final_pass) {
    // SDK #507: retain format so the final pipeline is reused every frame.
    paint_context_.guest_output_paint_pipelines[size_t(effect)].swapchain_format=paint_context_.swapchain_render_pass_format;
    static std::atomic<unsigned> count{0};
    std::fprintf(stderr,"AsterPresenter: pipeline %u, filter=%s, format retained\n",++count,custom!=VK_NULL_HANDLE?filter:"bilinear");
  }
  return result;
}
}
