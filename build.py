from fontTools.designspaceLib import DesignSpaceDocument
from glyphsLib.cli import main
from fontTools.ttLib import newTable, TTFont
import shutil
import subprocess
import multiprocessing
import multiprocessing.pool
from pathlib import Path
import argparse
import ufo2ft, ufoLib2, os, glob
import fontmake.instantiator
import copy

def DSIG_modification(font:TTFont):
    font["DSIG"] = newTable("DSIG")     #need that stub dsig
    font["DSIG"].ulVersion = 1
    font["DSIG"].usFlag = 0
    font["DSIG"].usNumSigs = 0
    font["DSIG"].signatureRecords = []
    font["head"].flags |= 1 << 3        #sets flag to always round PPEM to integer

def step_merge_glyphs_from_ufo(path: Path, instance: ufoLib2.Font, *args) -> None:
    textfile = ""
    for ar in args:
        textfile = ar

    ufo = ufoLib2.Font.open(path)
    if textfile:
        glyphSet = Path(textfile).read_text().split(" ")
        for glyph in glyphSet:
            instance.addGlyph(ufo[glyph])
    else:
        for glyph in ufo:
            if glyph.name not in instance:
                instance.addGlyph(ufo[glyph.name])

def make_static(instance_descriptor, generator):
    instance1 = generator.generate_instance(instance_descriptor)
    instance2 = copy.deepcopy(instance1)

    instance1.info.familyName = "Zen Kaku Gothic N"
    instance2.info.familyName = "Zen Kaku Gothic A"

    instance1.lib['com.github.googlei18n.ufo2ft.filters'] = [{ # extra safe :)
        "name": "flattenComponents",
        "pre": 1,
    }]
    instance2.lib['com.github.googlei18n.ufo2ft.filters'] = [{ # extra safe :)
        "name": "flattenComponents",
        "pre": 1,
    }]
    print ("["+instance_descriptor.name+"] Merging A and N kana")
    step_merge_glyphs_from_ufo(Path("sources/ZenKakuGothicN-"+instance_descriptor.styleName+".ufo"), instance1)
    step_merge_glyphs_from_ufo(Path("sources/ZenKakuGothicA-"+instance_descriptor.styleName+".ufo"), instance2)

    print ("["+instance_descriptor.name+"] Generating")

    N_ttf = ufo2ft.compileTTF(
        instance1, 
        removeOverlaps=True, 
        overlapsBackend="pathops", 
        useProductionNames=True,
    )

    A_ttf = ufo2ft.compileTTF(
        instance2, 
        removeOverlaps=True, 
        overlapsBackend="pathops", 
        useProductionNames=True,
    )

    DSIG_modification(A_ttf)
    DSIG_modification(N_ttf)
    print ("["+instance_descriptor.name+"] Saving")

    if instance_descriptor.styleName != "Regular":
        base_load = TTFont()
        TTFont.importXML(base_load, Path("sources/BASE-"+instance_descriptor.styleName+".ttx"))
        A_ttf["BASE"] = base_load["BASE"]
        N_ttf["BASE"] = base_load["BASE"]

    GASP_set(A_ttf)
    GASP_set(N_ttf)

    A_ttf.save("fonts/ttf/"+str(instance_descriptor.familyName).replace(" ","")+"A-"+instance_descriptor.styleName+".ttf")
    N_ttf.save("fonts/ttf/"+str(instance_descriptor.familyName).replace(" ","")+"N-"+instance_descriptor.styleName+".ttf")
            

def GASP_set(font:TTFont):
    if "gasp" not in font:
        font["gasp"] = newTable("gasp")
        font["gasp"].gaspRange = {}
    if font["gasp"].gaspRange != {65535: 0x000A}:
        font["gasp"].gaspRange = {65535: 0x000A}

def cleanup():
    # Cleanup
    for ufo in sources.glob("**/*.ufo"):
        shutil.rmtree(ufo)
    os.remove("sources/GothicA_Kana.designspace")
    os.remove("sources/GothicN_kana.designspace")
    os.remove("sources/ZenKakuGothic.designspace")


if __name__ == "__main__":
    sources = Path("sources")
    print ("[ZEN] Generating UFO sources")
    for file in sources.glob("**/*.glyphs"):
        print ("["+str(file)+"] generating source")
        main(("glyphs2ufo", str(file), "--write-public-skip-export-glyphs"))
    
    for ufo in sources.glob("*.ufo"): # need to put this command in all the source UFOs to make sure it is implemented
        source = ufoLib2.Font.open(ufo)
        source.lib['com.github.googlei18n.ufo2ft.filters'] = [{
            "name": "flattenComponents",
            "pre": 1,
        }]
        ufoLib2.Font.save(source)

    ds = DesignSpaceDocument.fromfile(sources / "ZenKakuGothic.designspace")
    ds.loadSourceFonts(ufoLib2.Font.open)
    generator = fontmake.instantiator.Instantiator.from_designspace(ds)

    pool = multiprocessing.pool.Pool(processes=multiprocessing.cpu_count())
    processes = []

    for instance_descriptor in ds.instances: # GOTTA GO FAST
        processes.append(
            pool.apply_async(
                make_static,
                (
                    instance_descriptor,
                    generator,
                ),
            )
        )

    pool.close()
    pool.join()
    for process in processes:
        process.get()
    del processes, pool

    print ("Cleaning build files")
    cleanup()