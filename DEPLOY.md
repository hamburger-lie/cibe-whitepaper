# 阿里云生产环境部署指南

本指南适用于将 CIBE 白皮书生成系统部署到阿里云 ECS (Ubuntu/CentOS) 服务器。

## 1. 服务器环境准备

### 1.1 安装 Python 3.9+

```bash
# Ubuntu
sudo apt update && sudo apt install -y python3 python3-pip python3-venv

# CentOS
sudo yum install -y python3 python3-pip
```

### 1.2 安装 Nginx

```bash
# Ubuntu
sudo apt install -y nginx

# CentOS
sudo yum install -y nginx
```

### 1.3 上传项目代码

```bash
# 方式一：从 GitHub 克隆
cd /opt
sudo git clone https://github.com/hamburger-lie/cibe-whitepaper.git
cd cibe-whitepaper

# 方式二：SCP 上传
scp -r ./cibe-whitepaper root@your-server-ip:/opt/cibe-whitepaper
```

### 1.4 安装 Python 依赖

```bash
cd /opt/cibe-whitepaper
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 1.5 配置环境变量

```bash
cp .env.example .env
vim .env
```

**必须修改的配置项：**

```env
# 填入你的 DeepSeek API Key
DEEPSEEK_API_KEY=sk-your-actual-key

# 填入你的豆包星绘 Key（可选）
ARK_API_KEY=your-ark-key

# 生产环境必须修改为随机强密钥！
# 可用命令生成：python3 -c "import secrets; print(secrets.token_urlsafe(48))"
JWT_SECRET=your-random-secret-key-here

# 允许的来源（改为你的实际域名）
ALLOWED_ORIGINS=https://yourdomain.com,http://yourdomain.com
```

## 2. 后台启动应用

### 2.1 使用 nohup 启动（简单方式）

```bash
cd /opt/cibe-whitepaper
source venv/bin/activate

# 仅监听本地回环地址（安全：外网无法直接访问 5678 端口）
nohup uvicorn proxy:app --host 127.0.0.1 --port 5678 &

# 查看日志
tail -f nohup.out
```

### 2.2 使用 systemd 服务（推荐，开机自启）

创建 service 文件：

```bash
sudo vim /etc/systemd/system/cibe-whitepaper.service
```

写入以下内容：

```ini
[Unit]
Description=CIBE Whitepaper Generator
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/cibe-whitepaper
Environment="PATH=/opt/cibe-whitepaper/venv/bin"
ExecStart=/opt/cibe-whitepaper/venv/bin/uvicorn proxy:app --host 127.0.0.1 --port 5678
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

启用并启动服务：

```bash
# 设置目录权限
sudo chown -R www-data:www-data /opt/cibe-whitepaper

# 启动
sudo systemctl daemon-reload
sudo systemctl enable cibe-whitepaper
sudo systemctl start cibe-whitepaper

# 查看状态
sudo systemctl status cibe-whitepaper

# 查看日志
sudo journalctl -u cibe-whitepaper -f
```

## 3. Nginx 反向代理配置

### 3.1 创建站点配置

```bash
sudo vim /etc/nginx/sites-available/cibe-whitepaper
```

写入以下内容（将 `yourdomain.com` 替换为你的实际域名或公网 IP）：

```nginx
server {
    listen 80;
    server_name yourdomain.com;

    # 安全头
    add_header X-Content-Type-Options nosniff;
    add_header X-Frame-Options DENY;
    add_header X-XSS-Protection "1; mode=block";

    # 请求体大小限制（支持大文件上传）
    client_max_body_size 50M;

    # 反向代理到 FastAPI
    location / {
        proxy_pass http://127.0.0.1:5678;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # 白皮书生成可能耗时较长
        proxy_read_timeout 300s;
        proxy_connect_timeout 10s;
    }
}
```

### 3.2 启用站点

```bash
# Ubuntu (sites-available/sites-enabled 模式)
sudo ln -s /etc/nginx/sites-available/cibe-whitepaper /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default

# CentOS (直接放在 conf.d 目录)
# sudo cp /etc/nginx/sites-available/cibe-whitepaper /etc/nginx/conf.d/cibe-whitepaper.conf
```

### 3.3 测试并重载 Nginx

```bash
sudo nginx -t
sudo systemctl reload nginx
```

此时访问 `http://yourdomain.com` 应该能看到登录页面。

## 4. 开启 HTTPS（Certbot + Let's Encrypt）

### 4.1 安装 Certbot

```bash
# Ubuntu
sudo apt install -y certbot python3-certbot-nginx

# CentOS
sudo yum install -y certbot python3-certbot-nginx
```

### 4.2 申请证书并自动配置 Nginx

```bash
sudo certbot --nginx -d yourdomain.com
```

按提示操作：
1. 输入邮箱（用于证书到期提醒）
2. 同意服务条款
3. 选择是否将 HTTP 重定向到 HTTPS（建议选 **是**）

Certbot 会自动修改 Nginx 配置，添加 SSL 相关指令。

### 4.3 验证 HTTPS

```bash
# 测试证书自动续期
sudo certbot renew --dry-run
```

访问 `https://yourdomain.com` 确认 HTTPS 正常工作。

### 4.4 设置自动续期

Certbot 安装时通常已自动添加定时任务，确认一下：

```bash
sudo systemctl status certbot.timer
# 或
sudo crontab -l | grep certbot
```

如果没有，手动添加：

```bash
echo "0 3 * * * certbot renew --quiet && systemctl reload nginx" | sudo crontab -
```

## 5. 阿里云安全组配置

在阿里云 ECS 控制台，确保安全组规则开放以下端口：

| 端口 | 协议 | 用途 |
|------|------|------|
| 80 | TCP | HTTP |
| 443 | TCP | HTTPS |
| 22 | TCP | SSH（建议限制来源 IP） |

**不要开放 5678 端口**，因为 Nginx 已做反向代理，FastAPI 只监听 127.0.0.1。

## 6. 常用运维命令

```bash
# 查看应用状态
sudo systemctl status cibe-whitepaper

# 重启应用
sudo systemctl restart cibe-whitepaper

# 查看实时日志
sudo journalctl -u cibe-whitepaper -f

# 重载 Nginx
sudo systemctl reload nginx

# 查看 Nginx 错误日志
sudo tail -f /var/log/nginx/error.log
```

## 7. 安全检查清单

- [ ] `.env` 中的 `JWT_SECRET` 已修改为随机强密钥
- [ ] `.env` 中的 `ALLOWED_ORIGINS` 已修改为实际域名
- [ ] 阿里云安全组未开放 5678 端口
- [ ] HTTPS 已启用并强制跳转
- [ ] SSH 端口已限制来源 IP
- [ ] `users.db` 文件权限已限制（`chmod 600`）
- [ ] Certbot 自动续期已配置
