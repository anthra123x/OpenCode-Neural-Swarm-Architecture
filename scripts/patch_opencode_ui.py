#!/usr/bin/env python3
"""
patch_opencode_ui.py — OpenCode Swarm Edition TUI Patcher

Applies surgical binary patches to OpenCode (Bun single-file executable)
with exact byte-length preservation:
1. LOGO: Adds "  ꜱᴡᴀʀᴍ" / "  ᴇᴅɪᴛɪᴏɴ" in matching block/small-caps styling
   right beside "opencode", matching Minecraft's "Java Edition" subtitle aesthetic.
2. PROMPT FOOTER: Injects the active project Web Cockpit session URL
   (e.g. "⚡ http://localhost:4040") into the location row directly below the prompt input.
"""

import sys
import os
import shutil
import subprocess

def find_system_opencode():
    # Priority paths for vanilla opencode binary
    candidates = [
        "/usr/bin/opencode",
        "/usr/local/bin/opencode",
        os.path.expanduser("~/.bun/bin/opencode"),
        os.path.expanduser("~/.npm-global/bin/opencode")
    ]
    for c in candidates:
        if os.path.isfile(c) and os.access(c, os.X_OK):
            # Ensure it is not our wrapper script
            try:
                with open(c, "rb") as f:
                    header = f.read(4)
                    if header == b"\x7fELF":
                        return c
            except Exception:
                continue

    # Fallback to which
    which_out = shutil.which("opencode")
    if which_out:
        try:
            with open(which_out, "rb") as f:
                if f.read(4) == b"\x7fELF":
                    return which_out
        except Exception:
            pass
    return None

def patch_binary(src_path, dst_path):
    print(f"[*] Reading source binary: {src_path}")
    with open(src_path, "rb") as f:
        data = bytearray(f.read())

    patched_something = False

    # --- 1. Patch Logo: Search for ASCII block art invariant ---
    # Invariant right line containing "opencode" right wing:
    anchor_logo = b'"\\u2588___ \\u2588__\\u2588 \\u2588__\\u2588 \\u2588^^^","\\u2580\\u2580\\u2580\\u2580 \\u2580\\u2580\\u2580\\u2580 \\u2580\\u2580\\u2580\\u2580 \\u2580\\u2580\\u2580\\u2580"'
    pos_logo = data.find(anchor_logo)
    if pos_logo != -1:
        orig_logo = bytes(data[pos_logo:pos_logo + len(anchor_logo)])
        cand_logo = b'"\\u2588___ \\u2588__\\u2588 \\u2588__\\u2588 \\u2588^^^  SWARM",("\\u2580\\u2580\\u2580\\u2580 ".repeat(3)+"\\u2580\\u2580\\u2580\\u2580  EDITION"'
        diff_logo = len(orig_logo) - len(cand_logo) - 1
        if diff_logo >= 0:
            cand_logo_padded = cand_logo + b' ' * diff_logo + b')'
            if len(cand_logo_padded) == len(orig_logo):
                data[pos_logo:pos_logo + len(anchor_logo)] = cand_logo_padded
                print(f"[✓] Patched OpenCode logo with Minecraft-style 'SWARM EDITION' subtitle ({len(orig_logo)} bytes, pure ASCII)")
                patched_something = True
    else:
        # Fallback to legacy variable search if present
        pos_am = data.find(b"am={left:")
        end_am = data.find(b"u0={left:")
        if pos_am != -1 and end_am != -1 and pos_am < end_am:
            orig_am = bytes(data[pos_am:end_am])
            orig_am_len = len(orig_am)
            cand_am = b"""am={left:["                   ","\\u2588\\u2580\\u2580\\u2588 \\u2588\\u2580\\u2580\\u2588 \\u2588\\u2580\\u2580\\u2588 \\u2588\\u2580\\u2580\\u2584","\\u2588__\\u2588 \\u2588__\\u2588 \\u2588^^^ \\u2588__\\u2588","\\u2580\\u2580\\u2580\\u2580 \\u2588\\u2580\\u2580\\u2580 \\u2580\\u2580\\u2580\\u2580 \\u2580~~\\u2580"],right:["             \\u2584     ","\\u2588\\u2580\\u2580\\u2580 \\u2588\\u2580\\u2580\\u2588 \\u2588\\u2580\\u2580\\u2588 \\u2588\\u2580\\u2580\\u2588","\\u2588___ \\u2588__\\u2588 \\u2588__\\u2588 \\u2588^^^  SWARM","\\u2580\\u2580\\u2580\\u2580 ".repeat(3)+"\\u2580\\u2580\\u2580\\u2580  EDITION"]},"""
            diff_am = orig_am_len - len(cand_am)
            if diff_am >= 0:
                final_am = cand_am.replace(b"]},", b" " * diff_am + b"]},")
                if len(final_am) == orig_am_len:
                    data[pos_am:end_am] = final_am
                    print(f"[✓] Patched OpenCode logo via legacy array ({orig_am_len} bytes)")
                    patched_something = True

    # --- 2. Patch Prompt Footer Location / Session Web URL ---
    orig_prompt = b',wn=c(()=>{if(!r.sessionID)return W.ref??R.location.default();if(ye()!=="idle")return;return R.session.get(r.sessionID)?.location}),jo=c(()=>{let Ie=Le(),Ze=Ie?{directory:Ie}:wn();if(!Ze)return;let ht=Zl(Ze.directory,T.home),ut=R.location.vcs.info(Ze)?.branch.current;return ut?`${ht}:${ut}`:ht}),[qo,rn]=P(xe().width),dn=c(()=>{let Ie=jo();if(!Ie)return;return g$(Ie,qo())}),Kr='
    pos_prompt = data.find(orig_prompt)
    if pos_prompt != -1:
        orig_prompt_len = len(orig_prompt)
        cand_prompt = b',wn=c(()=>r.sessionID?ye()=="idle"?R.session.get(r.sessionID)?.location:void 0:W.ref??R.location.default()),jo=c(()=>{let d=Le()||wn()?.directory;if(!d)return;let h=Zl(d,T.home),b=R.location.vcs.info({directory:d})?.branch.current;return(b?h+":"+b:h)+"  "+(process.env.OPENCODE_WEB_URL||"http://localhost:4040")}),[qo,rn]=P(xe().width),dn=c(()=>jo()?g$(jo(),qo()):void 0)    ,Kr='
        if len(cand_prompt) == orig_prompt_len:
            data[pos_prompt:pos_prompt + orig_prompt_len] = cand_prompt
            print(f"[✓] Patched prompt footer location with active Web Cockpit URL ({orig_prompt_len} bytes)")
            patched_something = True
    else:
        # Check legacy pattern
        orig_legacy = b"""dn=c(()=>{if(!r.sessionID)return _.ref??C.location.default();if(ne()!=="idle")return;return C.session.get(r.sessionID)?.location}),zr=c(()=>{let Ie=Xe(),et=Ie?{directory:Ie}:dn();if(!et)return;let X=Al(et.directory,T.home),de=C.location.vcs.info(et)?.branch.current;return de?`${X}:${de}`:X}),[fn,gn]=w(se().width),_r=c(()=>{let Ie=zr();if(!Ie)return;return wL(Ie,fn())})"""
        pos_legacy = data.find(orig_legacy)
        if pos_legacy != -1:
            orig_legacy_len = len(orig_legacy)
            cand_legacy = b"""dn=c(()=>!r.sessionID?_.ref??C.location.default():ne()=="idle"?C.session.get(r.sessionID)?.location: void 0),zr=c(()=>{let I=Xe(),e=I?{directory:I}:dn();if(!e)return;let X=Al(e.directory,T.home),b=C.location.vcs.info(e)?.branch.current;return b?X+":"+b:X}),[fn,gn]=w(se().width),_r=c(()=>{let I=zr(),u=process.env.OPENCODE_WEB_URL;return I?wL(I,fn())+(u?`  ${u}`:""):void 0})"""
            if len(cand_legacy) == orig_legacy_len:
                data[pos_legacy:pos_legacy + orig_legacy_len] = cand_legacy
                print(f"[✓] Patched legacy prompt footer location ({orig_legacy_len} bytes)")
                patched_something = True
        else:
            print("[*] Prompt footer in-binary patch skipped (active Cockpit URL handled via session launcher wrapper)")

    if not patched_something:
        print("[!] Warning: Could not locate patch targets in binary")
        return False

    # Ensure output directory exists and write atomically to avoid [Errno 26] Text file busy
    os.makedirs(os.path.dirname(os.path.abspath(dst_path)), exist_ok=True)
    tmp_path = dst_path + f".tmp.{os.getpid()}"
    with open(tmp_path, "wb") as f:
        f.write(data)
    os.chmod(tmp_path, 0o755)
    os.replace(tmp_path, dst_path)
    print(f"[✓] Saved Swarm Edition binary to: {dst_path}")
    return True

def main():
    dest = os.path.expanduser("~/.config/opencode/bin/opencode-swarm")
    src = find_system_opencode()

    if len(sys.argv) == 2:
        dest = sys.argv[1]
    elif len(sys.argv) >= 3:
        a1, a2 = sys.argv[1], sys.argv[2]
        if a1.startswith("/usr") or "swarm" in a2:
            src, dest = a1, a2
        else:
            dest, src = a1, a2

    if not src or not os.path.isfile(src):
        print("[!] Could not locate system opencode ELF executable to patch.")
        sys.exit(1)

    success = patch_binary(src, dest)
    if not success:
        print("[!] Failed to patch OpenCode binary.")
        sys.exit(1)

    # Test run
    try:
        res = subprocess.run([dest, "--version"], capture_output=True, text=True, timeout=5)
        if res.returncode == 0:
            print(f"[✓] Binary verified successfully: {res.stdout.strip()}")
            sys.exit(0)
        else:
            print(f"[!] Verification failed: {res.stderr}")
            sys.exit(1)
    except Exception as e:
        print(f"[!] Verification execution error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
