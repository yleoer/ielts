# 使用官方 Golang 镜像作为构建环境
FROM golang:1.21-alpine AS builder

# 安装必要的构建工具
RUN apk add --no-cache gcc musl-dev sqlite-dev

# 设置工作目录
WORKDIR /app

# 复制 go.mod 和 go.sum
COPY go.mod go.sum ./

# 下载依赖
RUN go mod download

# 复制源代码
COPY . .

# 构建应用
RUN CGO_ENABLED=1 GOOS=linux go build -a -installsuffix cgo -o typing-practice .

# 使用轻量级镜像作为运行环境
FROM alpine:latest

# 安装运行时依赖
RUN apk --no-cache add ca-certificates sqlite-libs

WORKDIR /root/

# 从构建阶段复制二进制文件
COPY --from=builder /app/typing-practice .

# 创建数据目录
RUN mkdir -p /root/data

# 暴露端口
EXPOSE 8080

# 设置环境变量
ENV ANKI_DB_PATH=/root/data/collection.anki2
ENV SERVER_PORT=8080
ENV GIN_MODE=release

# 运行应用
CMD ["./typing-practice"]
