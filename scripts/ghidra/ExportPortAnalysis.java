// Local static analysis only. Does not execute any game code.
// @category Aster
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.*;
import com.google.gson.GsonBuilder;
import java.nio.file.*;
import java.util.*;
public class ExportPortAnalysis extends GhidraScript {
    @Override public void run() throws Exception {
        String language = currentProgram.getLanguageID().toString();
        if (!language.equals("PowerPC:BE:64:A2ALT-32addr"))
            throw new IllegalStateException("Wrong language: " + language);
        Map<String,Object> report = new LinkedHashMap<>();
        report.put("language", language);
        report.put("input_md5", currentProgram.getExecutableMD5());
        report.put("compiler", currentProgram.getCompilerSpec().getCompilerSpecID().toString());
        report.put("image_base", currentProgram.getImageBase().toString());
        report.put("function_count", currentProgram.getFunctionManager().getFunctionCount());
        report.put("executed_game", false);
        List<Object> blocks = new ArrayList<>();
        for (var block: currentProgram.getMemory().getBlocks()) {
            Map<String,Object> item = new LinkedHashMap<>();
            item.put("name", block.getName()); item.put("start", block.getStart().toString());
            item.put("size", block.getSize()); item.put("execute", block.isExecute());
            blocks.add(item);
        }
        report.put("memory_blocks", blocks);
        List<Object> functions = new ArrayList<>();
        var iter = currentProgram.getFunctionManager().getFunctions(true);
        while (iter.hasNext() && !monitor.isCancelled()) {
            Function fn = iter.next();
            Map<String,Object> item = new LinkedHashMap<>();
            item.put("address", fn.getEntryPoint().toString()); item.put("name", fn.getName());
            item.put("body_bytes", fn.getBody().getNumAddresses());
            item.put("end", fn.getBody().getMaxAddress().toString());
            functions.add(item);
        }
        report.put("functions", functions);
        List<Object> entry = new ArrayList<>();
        if (getScriptArgs().length < 2) throw new IllegalArgumentException("Pass output JSON and verified entry address");
        var address = toAddr(Long.decode(getScriptArgs()[1]));
        for(int i=0;i<32;i++) {
            Instruction insn = currentProgram.getListing().getInstructionAt(address);
            if(insn==null) break;
            entry.add(address + " " + insn.toString()); address = insn.getMaxAddress().next();
        }
        report.put("entry_instructions", entry);
        Files.writeString(Path.of(getScriptArgs()[0]), new GsonBuilder().setPrettyPrinting().create().toJson(report));
        println("ASTER_ANALYSIS_EXPORTED functions=" + functions.size() + " language=" + language);
    }
}
