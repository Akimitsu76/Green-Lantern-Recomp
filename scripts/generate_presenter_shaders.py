#!/usr/bin/env python3
"""Rebuild and validate public presenter shaders; requires glslangValidator/spirv-val."""
from pathlib import Path
import struct
import subprocess
import tempfile


def main():
    directory=Path(__file__).resolve().parents[1]/'integrations/rexglue/presenter-filter'
    variants=[('spatial.frag','cubic',[]),('spatial.frag','sharp',['-DASTER_SHARP=1']),
              ('fsr_easu.frag','fsr_easu',[])]
    with tempfile.TemporaryDirectory(prefix='aster-shaders-') as temporary:
        for source,name,defines in variants:
            for dither in (False,True):
                variant=name+('_dither' if dither else '')
                output=Path(temporary)/(variant+'.spv')
                subprocess.run(['glslangValidator','-V','-I'+str(directory),*defines,
                                *(['-DASTER_DITHER=1'] if dither else []),str(directory/source),'-o',str(output)],check=True)
                subprocess.run(['spirv-val',str(output)],check=True)
                data=output.read_bytes();words=struct.unpack('<'+'I'*(len(data)//4),data)
                lines=[','.join(hex(w) for w in words[i:i+8])+',' for i in range(0,len(words),8)]
                origin='AMD EASU; see FSR-LICENSE.txt.' if name=='fsr_easu' else 'Original Aster shader.'
                (directory/(variant+'_spirv.h')).write_text('// Generated from '+source+' with glslangValidator -V. '+origin+'\nstatic constexpr uint32_t '+variant+'_spirv[] = {\n  '+'\n  '.join(lines)+'\n};\n')

if __name__=='__main__': main()
