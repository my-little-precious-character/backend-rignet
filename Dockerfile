FROM python:3.7-slim

######## RigNet ########

RUN apt update && apt upgrade -y && \
    apt -y install git unzip libgl1 libglib2.0-0 build-essential libxmu6 libglu1-mesa xvfb libspatialindex-dev && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip && \
    pip install \
        gdown \
        trimesh \
        open3d \
        opencv-python \
        tensorboard \
        rtree

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

RUN sed -i 's/ -pb//g' quick_start.py && \
    sed -i 's/"cuda:0" if torch.cuda.is_available() else //g' quick_start.py && \
    sed -i "s/torch.load(\([^,)]*\))/torch.load(\1, map_location='cpu')/g" quick_start.py && \
    sed -i 's|./binvox|xvfb-run ./binvox|g' quick_start.py && \
    sed -i 's/^[[:space:]]*img = show_obj_skel(.*)$/        pass/' quick_start.py

######## FastAPI ########

# Install uv
RUN apt update && \
    apt install -y wget && \
    rm -rf /var/lib/apt/lists/*
ADD https://astral.sh/uv/install.sh /uv-installer.sh
RUN sh /uv-installer.sh && rm /uv-installer.sh
ENV PATH="/root/.local/bin/:$PATH"

WORKDIR /app
COPY . .

RUN uv sync --locked

CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
