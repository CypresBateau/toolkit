# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

MAVL（多维视觉语言预训练）是用于胸部 X 光分析的医疗 AI 框架，已被 CVPR 2024 收录。通过 LLM 生成的视觉概念将疾病描述分解为多个视觉维度，在 7 个医疗数据集上实现了零样本和少样本 SOTA 性能。

**核心技术：**
- 视觉编码器：ResNet-50 或 ViT
- 文本编码器：Bio_ClinicalBERT（`emilyalsentzer/Bio_ClinicalBERT`）
- 交叉注意力解码器（4 层，4 头），将视觉特征与 75 个疾病查询对齐
- 多维学习：每种疾病由 GPT-4 生成 7 个视觉概念

**核心知识库：**
- 75 个疾病观察（"disease book"）— `observation explanation.json`
- 51 个解剖位置（"anatomy book"）
- 每病 7 个视觉概念（"concept book"）— `Pretrain/concept_gen/gpt4_mimic.json`
  - 数据集专用变体：`gpt4_mimic_covidr.json`、`gpt4_mimic_padchest_rare.json`

**以下所有命令均在 `MAVL/` 子目录下执行。**

## 环境搭建

```bash
# Docker（推荐）
docker pull stevephan46/mavl:latest
docker run --runtime=nvidia --name mavl -it -v /your/data/root/folder:/data --shm-size=4g stevephan46/mavl:latest
# 可能需要重新安装：pip install opencv-python==4.2.0.32

# 手动安装
pip install -r requirements.txt
pip install torch==1.12.0+cu113 torchvision==0.13.0+cu113 torchaudio==0.12.0 --extra-index-url https://download.pytorch.org/whl/cu113
pip install opencv-python==4.2.0.32
```

## 数据准备

```bash
bash download.sh  # 从 Google Drive 下载预处理数据
# 预处理数据文件：https://drive.google.com/drive/folders/1EN-oHVk513qmoehWypkrJ2Ero5PoUmId
# MIMIC-CXR-JPG 2.0.0 需单独从 physionet.org 下载
```

## 运行命令

### 预训练（MIMIC-CXR-JPG）
```bash
# 完整训练（4 × A100，60 epochs）
accelerate launch --multi_gpu --num_processes=4 --num_machines=1 --num_cpu_threads_per_process=8 train_MAVL.py --root /data/2019.MIMIC-CXR-JPG/2.0.0 --config configs/MAVL_resnet.yaml --bs 124 --num_workers 8

# 轻量训练（2 × A100，40 epochs，混合精度）
accelerate launch --multi_gpu --num_processes=2 --num_machines=1 --num_cpu_threads_per_process=8 --mixed_precision=fp16 train_MAVL.py --root /data/2019.MIMIC-CXR-JPG/2.0.0 --config configs/MAVL_short.yaml --bs 124 --num_workers 8
```

### 零样本分类
```bash
cd Zero-shot_classification
python test.py --config configs/chexpert_mavl.yaml
# 指定 GPU：CUDA_VISIBLE_DEVICES=0 python test.py --config configs/chexpert_mavl.yaml
```

### 零样本定位
```bash
cd Zero-shot_grounding
python test.py
```

### 微调
```bash
# 分类
cd Finetuning/classification
python train_res_ft.py --config configs/chexpert_mavl.yaml
python test_res_ft.py --config configs/chexpert_mavl.yaml

# 分割
cd Finetuning/segmentation
python train_res_ft.py --config configs/siim_mavl.yaml
```

## 架构说明

### 训练流程
1. 视觉编码器从 224×224 胸片中提取 patch 特征
2. 文本编码器（Bio_ClinicalBERT）编码疾病描述 + 视觉概念
3. 交叉注意力解码器将视觉特征与 75 个疾病查询对齐
4. 三个损失函数：
   - 交叉熵损失：疾病存在预测
   - 对比损失：解剖位置预测（51 个位置，temp=0.07，queue=8192）
   - 全局对比损失：概念对齐

**关键维度：** 嵌入=256，查询数=75，注意力头=4，解码器层=4，每病概念数=8（7 个视觉 + 1 个基础）

**标签编码：** -1=未知，0=阴性，1=阳性，2=排除

### 关键模型文件
- `Pretrain/models/model_MAVL.py` — MAVL 主模型
- `Pretrain/models/model_MedKLIP.py` — MedKLIP 基线（可通过 `train_MedKLIP.py` 训练）
- `Pretrain/models/transformer.py` — 交叉注意力解码器
- `Pretrain/models/loss.py` — 所有损失函数

### 配置文件规则
配置文件命名格式：`{dataset}_{model}.yaml`。关键字段：
- `test_file`：含图像路径和标签的 CSV 文件
- `root`：数据根目录
- `model_path`：checkpoint 文件路径
- `dataset`：数据集类型（`chexpert`、`chestxray14`、`padchest`、`rsna`、`siim`、`covid-cxr2`、`covid-r`）
- `mode`：`feature`（局部交叉注意力特征，推荐）或 `text`（全局 BERT 特征）
- `test_batch_size`：默认 256；显存 ≤8GB 时建议调整为 32–64

## Checkpoint 选择

| Checkpoint | 最佳适用场景 |
|---|---|
| `checkpoint_full_46.pth` | 零样本分类 |
| `checkpoint_full_40.pth` | 视觉定位 |

每 3 个 epoch 保存一次，以验证损失最低为准保存最优 checkpoint；warmup 5 epochs。

## 自定义数据 / 单张图像推理

原始代码需通过 CSV 批量推理。自定义数据的处理方式：

1. **创建最小 CSV**（标签未知时可全填 `0`，仅用于评估）：
   ```csv
   image_path,Enlarged Cardiomediastinum,Cardiomegaly,...
   patient001.jpg,0,0,...
   ```
2. 将 `root` 指向图像目录，`test_file` 指向 CSV，设置 `dataset: chexpert`
3. 运行 `python test.py --config configs/my_data_mavl.yaml`

结果保存至 `result_{model}_{dataset}_{mode}.csv` 和 `results/{model_name}.csv`。

输入图像：RGB 格式 JPG/PNG（自动缩放至 224×224）。RSNA 数据集支持 DICOM `.dcm` 文件（通过 pydicom 自动直方图均衡化）。

## 实验追踪

- **WandB** 和 **TensorBoardX** 已集成于 `train_MAVL.py`
- 分布式训练使用 **HuggingFace Accelerate**

## 视觉概念生成

通过 GPT-4 生成视觉概念，入口 notebook：`Pretrain/concept_gen/concept_init.ipynb`
提示词模板：`visual_prompts.txt`、`umls_prompts.txt`
