// @category Aster
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.listing.*;
import com.google.gson.GsonBuilder;
import java.nio.file.*;
import java.util.*;
public class ExportSelectedFunctions extends GhidraScript {
    @Override public void run() throws Exception {
        String[] args=getScriptArgs();
        if(args.length<2)throw new IllegalArgumentException("OUTPUT_JSON ADDRESS...");
        if(!currentProgram.getLanguageID().toString().equals("PowerPC:BE:64:A2ALT-32addr"))
            throw new IllegalStateException("Wrong PowerPC language");
        var decompiler=new DecompInterface();
        decompiler.openProgram(currentProgram);
        List<Object> results=new ArrayList<>();
        for(int i=1;i<args.length;i++) {
            var address=toAddr(Long.decode(args[i]));
            Map<String,Object> item=new LinkedHashMap<>();
            item.put("address",address.toString());
            Function fn=currentProgram.getFunctionManager().getFunctionAt(address);
            if(fn!=null) {
                item.put("name",fn.getName());item.put("body_bytes",fn.getBody().getNumAddresses());
                var result=decompiler.decompileFunction(fn,60,monitor);
                item.put("decompile_completed",result.decompileCompleted());
                item.put("error",result.getErrorMessage());
                if(result.getDecompiledFunction()!=null)item.put("pseudocode",result.getDecompiledFunction().getC());
            }
            List<String> instructions=new ArrayList<>();
            var at=address;
            for(int n=0;n<24;n++) {
                var insn=currentProgram.getListing().getInstructionAt(at);
                if(insn==null)break;
                instructions.add(at+" "+insn);at=insn.getMaxAddress().next();
                if(insn.getFlowType().isTerminal())break;
            }
            item.put("instructions",instructions);
            List<String> refs=new ArrayList<>();
            var iter=currentProgram.getReferenceManager().getReferencesTo(address);
            while(iter.hasNext())refs.add(iter.next().getFromAddress().toString());
            item.put("incoming_reference_addresses",refs);
            results.add(item);
        }
        decompiler.dispose();
        Files.writeString(Path.of(args[0]),new GsonBuilder().setPrettyPrinting().create().toJson(results));
        println("ASTER_SELECTED_EXPORTED count="+results.size());
    }
}
