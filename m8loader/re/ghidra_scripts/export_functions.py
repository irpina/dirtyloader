# Ghidra post-analysis script (headless). Exports discovered functions and a few
# anchor strings to JSON so dirtyloader can reason about hook targets.
#
# Runs under Ghidra's scripting runtime (Jython or PyGhidra); the flat-API
# globals (currentProgram, getScriptArgs, etc.) are injected by GhidraScript.
#
# Invoked by analyzeHeadless as:  -postScript export_functions.py <out.json>
import json

args = getScriptArgs()
out = args[0] if args and len(args) > 0 else "ghidra_functions.json"

fm = currentProgram.getFunctionManager()
funcs = []
it = fm.getFunctions(True)
while it.hasNext():
    f = it.next()
    ep = f.getEntryPoint()
    funcs.append({
        "name": f.getName(),
        "entry": "0x%08X" % ep.getOffset(),
        "size": int(f.getBody().getNumAddresses()),
        "thunk": bool(f.isThunk()),
    })

# a few defined strings, to confirm data recovery and give anchor references
strings = []
listing = currentProgram.getListing()
di = listing.getDefinedData(True)
count = 0
while di.hasNext() and count < 200:
    d = di.next()
    try:
        if d.hasStringValue():
            v = d.getValue()
            s = v.getStringValue() if hasattr(v, "getStringValue") else str(v)
            if s and len(s) >= 4:
                strings.append({"addr": "0x%08X" % d.getAddress().getOffset(),
                                "text": s[:60]})
                count += 1
    except Exception:
        pass

summary = {
    "program": currentProgram.getName(),
    "language": str(currentProgram.getLanguageID()),
    "image_base": "0x%08X" % currentProgram.getImageBase().getOffset(),
    "function_count": len(funcs),
    "string_sample_count": len(strings),
    "functions": funcs,
    "strings": strings,
}

fh = open(out, "w")
json.dump(summary, fh, indent=2)
fh.close()
print("dirtyloader: exported %d functions, %d strings -> %s" % (len(funcs), len(strings), out))
