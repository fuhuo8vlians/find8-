import os
import re
import subprocess
import tldextract
import concurrent.futures

# 后缀列表
SUFFIXES = [
    ".zip", ".rar", ".tar.gz", ".tgz", ".sql", 
    ".bak", ".7z", ".war", ".tar", ".gz"
]

def process_url(url):
    """处理单个URL，提取域名并生成组合"""
    # 移除协议前缀
    url_clean = re.sub(r'^https?://', '', url)
    # 移除路径和参数
    domain_part = url_clean.split('/')[0]
    
    # 使用tldextract提取域名部分
    extracted = tldextract.extract(domain_part)
    
    # 提取主域名（如baidu.com）
    main_domain = f"{extracted.domain}.{extracted.suffix}"
    
    # 如果有子域名，提取子域名
    subdomain = None
    if extracted.subdomain:
        subdomain = f"{extracted.subdomain}.{main_domain}"
    
    # 生成组合
    combinations = []
    
    # 主域名组合
    for suffix in SUFFIXES:
        combinations.append(f"{main_domain}{suffix}")
    
    # 子域名组合（如果存在）
    if subdomain:
        for suffix in SUFFIXES:
            combinations.append(f"{subdomain}{suffix}")
    
    return url, combinations

def main():
    # 输入和输出文件路径
    url_file = "url.txt"
    bak_file = "bak.txt"
    output_file = "bak2.txt"
    result_file = "res.json"
    
    # 读取URL列表
    urls = []
    if os.path.exists(url_file):
        with open(url_file, 'r', encoding='utf-8') as f:
            urls = [line.strip() for line in f if line.strip()]
    else:
        print(f"错误：未找到URL文件 {url_file}")
        return
    
    print(f"读取到 {len(urls)} 个URL")
    
    # 处理每个URL（使用线程池加速）
    all_combinations = []
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future_to_url = {executor.submit(process_url, url): url for url in urls}
        for future in concurrent.futures.as_completed(future_to_url):
            url = future_to_url[future]
            try:
                _, combinations = future.result()
                all_combinations.extend(combinations)
            except Exception as e:
                print(f"处理URL {url} 时出错: {e}")
    
    # 读取bak.txt内容
    bak_content = []
    if os.path.exists(bak_file):
        with open(bak_file, 'r', encoding='utf-8') as f:
            bak_content = [line.strip() for line in f if line.strip()]
    
    # 合并所有内容并写入bak2.txt
    all_content = all_combinations + bak_content
    
    with open(output_file, 'w', encoding='utf-8') as f:
        for item in all_content:
            f.write(item + '\n')
    
    print(f"已生成 {len(all_content)} 个组合，保存到 {output_file}")
    
    # 执行spray.exe工具
    try:
        cmd = [
            "spray.exe", 
            "-l", url_file, 
            "-d", output_file, 
            "-f", result_file
        ]
        
        print(f"执行命令: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            print(f"工具执行成功，结果保存到 {result_file}")
            print("输出信息:", result.stdout)
        else:
            print(f"工具执行失败，错误代码: {result.returncode}")
            print("错误信息:", result.stderr)
    
    except Exception as e:
        print(f"执行spray.exe时发生错误: {e}")

if __name__ == "__main__":
    main()
