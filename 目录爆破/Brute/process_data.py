import json
import pandas as pd
import os

def extract_names(data):
    names = []
    try:
        if isinstance(data, str):
            data = json.loads(data)
        for key, value in data.items():
            if isinstance(value, dict) and 'name' in value:
                names.append(value['name'])
    except (json.JSONDecodeError, AttributeError, TypeError):
        print(f"处理数据 {data} 时出现错误")
    return ' | '.join(names)

def process_data(input_file, output_file):
    try:
        data_list = []
        with open(input_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    data = json.loads(line)
                    data_list.append(data)
                except json.JSONDecodeError:
                    print(f"解析 JSON 行时出错: {line}")

        df = pd.DataFrame(data_list)
        df = df.map(lambda x: str(x).replace("'", "") if isinstance(x, (str, list)) else x)

        # 保存未处理 O 列的数据为 Excel 文件
        df.to_excel(output_file, index=False)
        print(f"初步文件保存完成，保存至 {output_file}")

        # 重新读取 Excel 文件
        df = pd.read_excel(output_file)

        # 处理 O 列数据
        if 'O' in df.columns:
            df['O'] = df['O'].apply(extract_names)

        # 再次保存处理后的文件
        df.to_excel(output_file, index=False)
        print(f"file has been save in {output_file}")

        # 新增工作流：提取第五列的URL并保存为同名TXT文件
        if len(df.columns) >= 5:
            # 获取第五列（索引为4）的数据
            url_column = df.iloc[:, 4]
            
            # 过滤掉空值并转换为列表
            urls = url_column.dropna().tolist()
            
            # 确保URL列表不为空
            if urls:
                # 构建与Excel文件同名的TXT文件路径
                base_name, _ = os.path.splitext(output_file)
                txt_output = f"{base_name}.txt"
                
                # 将URL列表写入TXT文件，每行一个URL
                with open(txt_output, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(urls))
                
                print(f"DesRedTeam")
            else:
                print("第五列中没有有效的URL数据")
        else:
            print("表格列数不足，无法提取第五列的URL")

    except Exception as e:
        print(f"处理文件时出现错误: {e}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        print("hello Des")
        sys.exit(1)
    input_file = sys.argv[1]
    output_file = sys.argv[2]
    process_data(input_file, output_file)