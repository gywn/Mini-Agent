# syntax=docker/dockerfile:1.4
# 使用 Debian 13 (trixie) slim 版
FROM debian:13-slim

ENV TZ=Asia/Shanghai
ENV DEBIAN_FRONTEND=noninteractive
ENV PIP_BREAK_SYSTEM_PACKAGES=1
ENV PIP_INDEX_URL=https://mirrors.sustech.edu.cn/pypi/web/simple
ENV DATA_GYM_CACHE_DIR=/root/data-gym-cache

# 安装必要的证书工具（需要先安装这些才能访问 HTTPS 镜像源）
RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates openssl && \
    rm -rf /var/lib/apt/lists/*

# 替换 Debian apt 源为 mirrors.sustech.edu.cn (在中国大陆访问更快)
COPY <<EOF /etc/apt/sources.list.d/debian.sources
Types: deb
URIs: https://mirrors.sustech.edu.cn/debian
Suites: trixie
Components: main contrib non-free
Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg

Types: deb
URIs: https://mirrors.sustech.edu.cn/debian
Suites: trixie-updates
Components: main contrib non-free
Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg

Types: deb
URIs: https://mirrors.sustech.edu.cn/debian-security
Suites: trixie-security
Components: main contrib non-free
Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg
EOF

# 安装必要工具：python3、pip、grep、curl
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    grep \
    jq \
    python3-pip \
    python3 \
    rsync \
    tree \
    tzdata && \
    rm -rf /var/lib/apt/lists/* && \
    # 安装 Python 依赖 \
    python3 -m pip install --no-cache-dir \
        anthropic>=0.39.0 \
        ast-grep-cli \
        black \
        httpx>=0.27.0 \
        isort \
        mcp>=1.0.0 \
        mypy \
        openai>=1.57.4 \
        pip>=25.1.1 \
        pipx>=1.8.0 \
        prompt-toolkit>=3.0.0 \
        pydantic>=2.0.0 \
        pytest>=8.4.2 \
        pyyaml>=6.0.0 \
        requests>=2.31.0 \
        tiktoken>=0.5.0 \
        w3lib>=2.1.0 && \
    # 缓存词嵌入数据 \
    python3 -c "import tiktoken; tiktoken.get_encoding('cl100k_base')"

# 设置容器内的工作目录为 /
WORKDIR /root/

# 将源码复制到镜像中并安装
COPY . /tmp/repo
RUN git -C /tmp/repo submodule update && \
    python3 -m pip install --no-cache-dir /tmp/repo && \
    PACKAGE_PATH=/usr/local/lib/python3.13/dist-packages/mini_agent && \
    mkdir ${PACKAGE_PATH}/config && \
    cp /tmp/repo/mini_agent/config/config-example.yaml ${PACKAGE_PATH}/config/config.yaml && \
    cp /tmp/repo/mini_agent/config/mcp-example.json ${PACKAGE_PATH}/config/mcp.json && \
    cp /tmp/repo/mini_agent/config/system_prompt.md ${PACKAGE_PATH}/config/system_prompt.md && \
    rm -rf /tmp/repo && \
    git config --global core.autocrlf true

# 运行时我们将把宿主机的当前目录挂载到这里
VOLUME /project

# 默认进入安装好的程序，方便交互
ENTRYPOINT ["/usr/local/bin/mini-agent", "--workspace=/project"]
