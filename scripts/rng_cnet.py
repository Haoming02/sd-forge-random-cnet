import logging
import os.path
import random
from glob import glob

import gradio as gr
import modules.scripts as scripts
import numpy as np
from modules.processing import StableDiffusionProcessing, fix_seed
from modules.ui_components import InputAccordion
from PIL import Image

logger = logging.getLogger("ControlNet")


class RNGCNet(scripts.Script):
    def title(self):
        return "Random ControlNet"

    def show(self, is_img2img):
        return scripts.AlwaysVisible

    def ui(self, is_img2img):
        with InputAccordion(False, label=self.title()) as enable:
            with gr.Row():
                folder_path = gr.Textbox(
                    value=None,
                    label="Images Folder",
                    lines=1,
                    max_lines=1,
                    info="absolute path is recommended",
                )
                with gr.Column():
                    recursive = gr.Checkbox(True, label="Include Subfolders")
                    random_subfolder = gr.Checkbox(True, label="Randomize by Subfolder")
            with gr.Row():
                force = gr.Checkbox(False, label="Force Enable ControlNet Unit 0")
                flip_h = gr.Checkbox(True, label="Randomly Flip Image Horizontally")
            with gr.Row():
                prompt_add = gr.Checkbox(True, label="Prompt Addition from .txt File")
                prompt_mod = gr.Checkbox(False, label="Prompt Replacement from .txt Content")

        comps = [
            enable,
            folder_path,
            recursive,
            random_subfolder,
            force,
            flip_h,
            prompt_add,
            prompt_mod,
        ]

        for comp in comps:
            comp.do_not_save_to_config = True

        return comps

    def setup(
        self,
        p: StableDiffusionProcessing,
        enable: bool,
        folder_path: str,
        recursive: bool,
        random_subfolder: bool,
        force: bool,
        flip_h: bool,
        prompt_add: bool,
        prompt_mod: bool,
    ):
        if not enable:
            return

        idx: int = self.fetch_index(p)
        unit_0 = p.script_args[idx]  # ControlNetUiGroup
        logger.debug("RNG Hooked~")

        if force:
            unit_0.enabled = True

        if not unit_0.enabled:
            logger.error("ControlNet is not enabled...")
            return

        if not os.path.isdir(folder_path):
            logger.error(f'Invalid Folder "{folder_path}"...')
            return

        objs: list[str] = glob(
            os.path.join(folder_path, *(["**", "*"] if recursive else ["*"])),
            recursive=recursive,
        )
        files: list[str] = [
            file
            for file in objs
            if file.endswith((".jpg", ".jpeg", ".png", ".webp", ".heif"))
        ]

        if len(files) == 0:
            logger.error(f'No images detected in folder "{folder_path}"...')
            return

        all_pools: list[list[str]] = []

        if not random_subfolder:
            all_pools.append(files)

        else:
            folders: dict[str, list[str]] = {}

            for file in files:
                folder = os.path.relpath(file, folder_path)
                group = folder.rsplit(os.sep, 1)[0]
                folders[group] = folders.get(group, []) + [file]

            for folder in folders.values():
                all_pools.append(folder)

        logger.info(f"Detected {len(all_pools)}x image pools")

        fix_seed(p)
        random.seed(p.seed)

        pool: list[str] = all_pools[random.randint(1, len(all_pools)) - 1]
        logger.info(f"Selected pool with {len(pool)}x images")

        image_path: str = pool[random.randint(1, len(pool)) - 1]

        image: Image.Image = Image.open(image_path).convert("RGB")

        if flip_h and random.randint(1, 2) == 2:
            image = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)

        img = np.asarray(image, dtype=np.uint8)
        msk = np.zeros((img.shape[0], img.shape[1]), dtype=np.uint8)

        unit_0.image = {"image": img, "mask": msk}
        text: str = ""

        text_path = os.path.splitext(image_path)[0] + ".txt"
        if os.path.isfile(text_path):
            with open(text_path, "r", encoding="utf-8") as f:
                text: str = f.read()

        else:
            text_path = os.path.join(os.path.dirname(image_path), "default.txt")
            if os.path.isfile(text_path):
                with open(text_path, "r", encoding="utf-8") as f:
                    text: str = f.read()

        if prompt_add and prompt_mod:
            logger.warning("Both Prompt Addition & Replacement are Enabled!")

        if text:
            if prompt_add:
                p.prompt += text
            if prompt_mod:
                p.prompt = p.prompt.replace("RNG", text)
        else:
            if prompt_add or prompt_mod:
                logger.warning("Failed to find a corresponding .txt File...")

    @staticmethod
    def fetch_index(p: StableDiffusionProcessing) -> int:
        script_runner: scripts.ScriptRunner = p.scripts
        controlnet: scripts.Script = next(
            (
                script
                for script in script_runner.alwayson_scripts
                if script.title() == "ControlNet"
            ),
            None,
        )

        if controlnet is None:
            raise SystemError("Could not find ControlNet...")
        else:
            return controlnet.args_from
