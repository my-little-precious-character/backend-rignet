FROM python:3.7-slim

RUN apt update && apt upgrade -y && \
    apt install git unzip libgl1 -y && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip && \
    pip install \
        gdown \
        trimesh \
        open3d

RUN pip install torch==1.12.0+cpu torchvision==0.13.0+cpu -f https://download.pytorch.org/whl/torch_stable.html && \
    pip install \
        torch-scatter \
        torch-sparse \
        torch-cluster \
        torch-spline-conv \
        -f https://data.pyg.org/whl/torch-1.12.0+cpu.html && \
    pip install torch-geometric==1.7.2

WORKDIR /workspace
RUN git clone https://github.com/zhan-xu/RigNet.git

WORKDIR /workspace/RigNet
RUN gdown 'https://drive.google.com/uc?id=1gM2Lerk7a2R0g9DwlK3IvCfp8c2aFVXs' -O trained_models.zip && \
    unzip trained_models.zip && \
    rm trained_models.zip

CMD ["/bin/bash"]
