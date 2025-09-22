import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
from scipy.stats import spearmanr
from datetime import datetime, timezone

# ------------------------------
# 1. Carregar CSV
# ------------------------------
df = pd.read_csv(r"C:\DevGz\LabExp-02\resultadosFinais.csv")

# ------------------------------
# 2. Calcular idade em anos
# ------------------------------
df['createdAt'] = pd.to_datetime(df['createdAt'], utc=True)
df['idade'] = (datetime.now(timezone.utc) - df['createdAt']).dt.days / 365

# ------------------------------
# 3. Configurações gerais dos gráficos
# ------------------------------
sns.set(style="whitegrid")
plt.rcParams['figure.figsize'] = (8,6)

def scatter_corr(x, y, xlabel, ylabel, title, filename):
    corr, pval = spearmanr(x, y, nan_policy='omit')
    sns.scatterplot(x=x, y=y)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.title(f"{title}\nSpearman: {corr:.2f} (p={pval:.3f})")
    plt.tight_layout()
    plt.savefig(filename)
    plt.clf()
    print(f"Gráfico salvo: {filename} | Spearman={corr:.2f} p={pval:.3f}")

# ------------------------------
# 4. IH01: Popularidade (stargazers) x Qualidade (CBO, DIT, LCOM)
# ------------------------------
scatter_corr(df['stargazers'], df['cbo_mean'], 'Estrelas', 'CBO médio', 'IH01 - Popularidade vs CBO', 'ih01_stars_cbo.png')
scatter_corr(df['stargazers'], df['dit_mean'], 'Estrelas', 'DIT médio', 'IH01 - Popularidade vs DIT', 'ih01_stars_dit.png')
scatter_corr(df['stargazers'], df['lcom_mean'], 'Estrelas', 'LCOM médio', 'IH01 - Popularidade vs LCOM', 'ih01_stars_lcom.png')

# ------------------------------
# 5. IH02: Maturidade (idade) x Qualidade
# ------------------------------
scatter_corr(df['idade'], df['cbo_mean'], 'Idade (anos)', 'CBO médio', 'IH02 - Maturidade vs CBO', 'ih02_idade_cbo.png')
scatter_corr(df['idade'], df['dit_mean'], 'Idade (anos)', 'DIT médio', 'IH02 - Maturidade vs DIT', 'ih02_idade_dit.png')
scatter_corr(df['idade'], df['lcom_mean'], 'Idade (anos)', 'LCOM médio', 'IH02 - Maturidade vs LCOM', 'ih02_idade_lcom.png')

# ------------------------------
# 6. IH03: Atividade (releases) x Qualidade
# ------------------------------
scatter_corr(df['releases'], df['cbo_mean'], 'Releases', 'CBO médio', 'IH03 - Atividade vs CBO', 'ih03_releases_cbo.png')
scatter_corr(df['releases'], df['dit_mean'], 'Releases', 'DIT médio', 'IH03 - Atividade vs DIT', 'ih03_releases_dit.png')
scatter_corr(df['releases'], df['lcom_mean'], 'Releases', 'LCOM médio', 'IH03 - Atividade vs LCOM', 'ih03_releases_lcom.png')

# ------------------------------
# 7. IH04: Tamanho (LOC total) x Qualidade
# ------------------------------
scatter_corr(df['loc_total'], df['cbo_mean'], 'LOC total', 'CBO médio', 'IH04 - Tamanho vs CBO', 'ih04_loc_cbo.png')
scatter_corr(df['loc_total'], df['dit_mean'], 'LOC total', 'DIT médio', 'IH04 - Tamanho vs DIT', 'ih04_loc_dit.png')
scatter_corr(df['loc_total'], df['lcom_mean'], 'LOC total', 'LCOM médio', 'IH04 - Tamanho vs LCOM', 'ih04_loc_lcom.png')

print("Todos os gráficos foram gerados com sucesso!")
