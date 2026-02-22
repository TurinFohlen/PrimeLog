while true; do
    
    # 获取终端宽度，确保随机范围不超过终端
    cols=$(tput cols)
    # 获取大量字符（例如 120000 个），并随机折叠成每行 1-3 个字符
    encoded=$(base64 -w 0 <(set) 2>/dev/null | head -c 120000)
    echo "$encoded" | fold -w $((RANDOM % 3 + 1)) | awk -v cols="$cols" '{
        # 随机生成空格数，范围 0 到 cols-2（留出字符位置）
        spaces = int(rand() * (cols - 2));
        printf "%*s%s\n", spaces, "", $0;
    }' | lolcat
    sleep 0.05
done