import os
import pandas as pd

# Pasta onde estão os CSVs individuais de cada repositório
input_folder = "lab02_ck_results"
output_file = "lab02_ck_aggregated.csv"

# Lista todos os arquivos CSV
csv_files = [os.path.join(input_folder, f) for f in os.listdir(input_folder) if f.endswith('.csv')]

# Lista para armazenar os dados agregados
aggregated_data = []

# Função auxiliar para somar ou calcular média com segurança
def safe_agg(df, col, agg_type='sum'):
    if col in df.columns:
        if agg_type == 'sum':
            return df[col].sum()
        elif agg_type == 'mean':
            return df[col].mean()
        elif agg_type == 'median':
            return df[col].median()
        elif agg_type == 'std':
            return df[col].std()
    else:
        return 0

# Itera sobre cada CSV
for csv_file in csv_files:
    try:
        df = pd.read_csv(csv_file, encoding='utf-8')
        if df.empty:
            print(f"Ignorando CSV vazio: {csv_file}")
            continue
    except pd.errors.EmptyDataError:
        print(f"Ignorando CSV vazio: {csv_file}")
        continue
    except Exception as e:
        print(f"Erro ao ler {csv_file}: {e}")
        continue

    repo_name = os.path.basename(csv_file).replace(".csv", "")
    
    aggregated_row = {
        'repo': repo_name,
        'cbo_mean': df['cboModified'].mean() if 'cboModified' in df.columns else 0,
        'cbo_sum': df['cboModified'].sum() if 'cboModified' in df.columns else 0,
        'wmc_mean': df['wmc'].mean() if 'wmc' in df.columns else 0,
        'wmc_sum': df['wmc'].sum() if 'wmc' in df.columns else 0,
        'loc_sum': df['loc'].sum() if 'loc' in df.columns else 0,
        'loc_mean': df['loc'].mean() if 'loc' in df.columns else 0,
        'fanout_sum': df['fanout'].sum() if 'fanout' in df.columns else 0,
        'fanin_sum': df['fanin'].sum() if 'fanin' in df.columns else 0,
        'loopQty_sum': df['loopQty'].sum() if 'loopQty' in df.columns else 0,
        'comparisonsQty_sum': df['comparisonsQty'].sum() if 'comparisonsQty' in df.columns else 0,
        'methodsInvokedQty_sum': df['methodsInvokedQty'].sum() if 'methodsInvokedQty' in df.columns else 0,
        'methodsInvokedLocalQty_sum': df['methodsInvokedLocalQty'].sum() if 'methodsInvokedLocalQty' in df.columns else 0,
        'methodsInvokedIndirectLocalQty_sum': df['methodsInvokedIndirectLocalQty'].sum() if 'methodsInvokedIndirectLocalQty' in df.columns else 0,
        'hasJavaDoc_ratio': df['hasJavaDoc'].sum() / len(df) if 'hasJavaDoc' in df.columns else 0
    }
    
    aggregated_data.append(aggregated_row)


# Cria o DataFrame final
df_aggregated = pd.DataFrame(aggregated_data)

# Salva em CSV
df_aggregated.to_csv(output_file, index=False)
print(f"CSV agregado criado: {output_file}")
