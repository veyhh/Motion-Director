---
name: motion-director
description: Generate real game animation on a rigged humanoid GLB or glTF using local Python and headless Blender. Use for character animation requests such as spear throwing, attack animation, or making a GLB animated; this MVP produces right-handed spear throws only.
---

# Motion Director

Turn a user's rigged character and spear-throw request into an animated GLB. Run the local
implementation in this skill directory. Do not use external AI APIs, cloud motion services,
or substitute an analysis report for an actual animation.

## Workflow

1. Locate the user's `.glb` or `.gltf` input. If several characters are plausible, ask which
   one. Do not substitute the bundled mannequin for their character. If no model is supplied,
   ask for one; the example mannequin is only for a requested demo.
2. Run `motion-director doctor`. If the command is unavailable, run `python -m pip install -e
   "<skill-directory>"`, or run `python -m motion_director` from that directory. Python 3.11+
   and local Blender 4+ are required. Use `--blender "<executable>"` when discovery fails.
3. Run `motion-director inspect "<input>"`. It must have exactly one humanoid armature and
   a weighted mesh. Review `missing`, `ambiguous`, and `hierarchy_errors`. A JSON mapping
   passed with `--mapping` can resolve names; it cannot create a missing rig.
4. Interpret the request. For an explicit spear throw, preserve the user's description and
   call the command below. Generic "attack" or "animate this GLB" does not identify a move:
   explain that this MVP supports spear throw and ask whether that is intended. Do not
   silently replace a requested sword attack, left-handed throw, or other unsupported move.
5. Create a new output directory for each attempt:

   ```bash
   motion-director create-animation "<input>" \
     "Bu karakter için güçlü bir mızrak fırlatma animasyonu yap." \
     --output "<new-output-directory>" --preview
   ```

   The command builds a procedural pose plan, runs Blender, keys real bones, creates
   `SpearThrow`, validates the poses, attempts one conservative correction if needed, exports
   GLB, and reopens it in a fresh Blender process. No Blender UI interaction is needed.
   Optional `--duration 0.9 --fps 50`; release timing is quantized to the actual frame.
6. Run `motion-director validate "<output>/<input-stem>_spear_throw.glb"`. Read
   `spear_throw.motion.json` and `spear_throw_report.md`. Verify `projectile_release`, duration,
   moving bones, and successful export/round-trip checks. A zero exit code from `inspect`
   alone does not mean an animation was generated.
7. Inspect `spear_throw_poses.png` or the MP4 when image/video inspection is available.
   Contact-sheet columns: Ready, WindUp, Release, FollowThrough; rows: three-quarter and side.
   Check the shoulder, elbow, hand position behind the head, forward release, torso, and feet.
   Numerical QA cannot prove that a mesh has no self-intersections. Do not claim visual review
   if it was not performed. PNG sequence fallback is a valid preview if video encoding fails.
8. If QA fails, read `spear_throw_failed_qa.json`. Correct a demonstrable mapping or recipe
   issue and regenerate into a **new directory**. Stop after one additional targeted attempt
   if the problem remains; report the actual failure and retain the original input. Never
   change a failed QA result to PASS or present a failed artifact as a ready animation.
9. Return clickable absolute paths to the animated GLB, motion JSON, report, and preview.
   Mention real remaining limitations. The JSON event tells the game when to spawn a
   projectile; the GLB does not add a spear object or projectile simulation.

## Runtime boundaries

- The original input is never overwritten. Existing outputs are refused. Imported clips
  are replaced by `SpearThrow` only in the new export; keep the input to retain them.
- Motion text selects a specialized deterministic recipe; this is not unrestricted natural
  language motion synthesis. Claude provides orchestration and interpretation, not an API call.
- Best supported: upright T/A-pose humanoids, two arm/leg chains, positive uniform object scale.
  Extra bones are retained but fingers and facial animation are not authored.
- Details, configuration, installation, QA limits, and test commands: [README.md](README.md).

