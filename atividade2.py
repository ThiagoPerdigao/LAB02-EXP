#!/usr/bin/env python3
"""
lab02s02_automacao.py

Automação Sprint 2 (Lab02S02):
 - Busca os top-1000 repositórios Java no GitHub (por estrelas)
 - Salva lista em lab02_repos.csv
 - Baixa cada repositório como ZIP em clones/
 - Baixa/compila CK (se necessário) e roda CK em cada repositório
 - Consolida resultados CK em lab02_ck_all.csv

Requisitos:
 - Python 3.7+
 - java (8+) no PATH
 - maven (se quiser que o script construa o JAR do CK automaticamente)
 - Definir GITHUB_TOKEN environment variable (ou editar TOKEN abaixo)
"""

import os
import sys
import time
import subprocess
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from io import BytesIO

import requests
import pandas as pd

# -----------------------
# CONFIGURAÇÕES
# -----------------------
TOKEN = "" # substitua ou defina GITHUB_TOKEN
GITHUB_GRAPHQL_URL = "https://api.github.com/graphql"
OUTPUT_REPOS_CSV = "lab02_repos.csv"
CLONES_DIR = Path("clones")
CK_REPO_DIR = Path("ck_tool")
CK_OUTPUT_BASE = Path("lab02_ck_results")
CK_LOCAL_JAR = CK_REPO_DIR / "target"
CK_JAR_GLOB = "ck-*-jar-with-dependencies.jar"
PER_PAGE = 50
TOTAL_REPOS = 1000
SLEEP_BETWEEN_PAGES = 1.0
CONSOLIDATED_CSV = "lab02_ck_all.csv"
# -----------------------

if TOKEN == "sua_token_aqui" or not TOKEN or TOKEN == "key":
    print("⚠️  Atenção: você deve definir um token do GitHub. Exporte GITHUB_TOKEN ou edite TOKEN no script.")
    sys.exit(1)

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "User-Agent": "Lab02-Coletor-Script"
}


def graphql_query(query: str, max_retries: int = 3, backoff: float = 5.0):
    for attempt in range(1, max_retries + 1):
        resp = requests.post(GITHUB_GRAPHQL_URL, json={"query": query}, headers=headers)
        print(f"GraphQL request status: {resp.status_code} (attempt {attempt})")
        if resp.status_code == 200:
            data = resp.json()
            if "errors" in data:
                raise RuntimeError(f"GraphQL errors: {data['errors']}")
            return data
        elif resp.status_code == 502 and attempt < max_retries:
            time.sleep(backoff)
            continue
        elif resp.status_code == 401:
            raise RuntimeError("401 Unauthorized — verifique seu token do GitHub.")
        else:
            print("Resposta:", resp.text[:400])
            time.sleep(backoff)
    raise RuntimeError("Falha ao executar GraphQL após múltiplas tentativas.")


def fetch_top_java_repos(total=1000, per_page=50):
    repos = []
    cursor = None
    collected = 0
    page = 1

    while collected < total:
        first = min(per_page, total - collected)
        after = f', after: "{cursor}"' if cursor else ""
        query = f"""
        {{
          search(query: "language:Java sort:stars-desc", type: REPOSITORY, first: {first}{after}) {{
            pageInfo {{
              endCursor
              hasNextPage
            }}
            edges {{
              node {{
                ... on Repository {{
                  nameWithOwner
                  url
                  createdAt
                  updatedAt
                  stargazerCount
                  primaryLanguage {{ name }}
                  releases {{ totalCount }}
                }}
              }}
            }}
          }}
          rateLimit {{
            limit
            cost
            remaining
            resetAt
          }}
        }}
        """

        data = graphql_query(query)
        search = data.get("data", {}).get("search")
        if not search:
            break

        edges = search.get("edges", [])
        for e in edges:
            node = e["node"]
            repos.append(node)
            collected += 1
            if collected >= total:
                break

        page_info = search.get("pageInfo", {})
        cursor = page_info.get("endCursor")
        has_next = page_info.get("hasNextPage", False)

        rl = data.get("data", {}).get("rateLimit")
        if rl:
            print(f"RateLimit remaining: {rl.get('remaining')} resetAt: {rl.get('resetAt')}")

        print(f"Página {page}: coletados até agora {collected}/{total}")
        page += 1
        if not has_next:
            break
        time.sleep(SLEEP_BETWEEN_PAGES)

    return repos[:total]


def save_repos_csv(repos, filename=OUTPUT_REPOS_CSV):
    df = pd.DataFrame(repos)
    df.to_csv(filename, index=False, encoding="utf-8")
    print(f"✅ Lista de repositórios salva em {filename} ({len(df)} linhas)")


def download_repo_zip(repo_full_name, dest_dir: Path):
    """Baixa o repositório como ZIP usando a branch padrão do GitHub."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / repo_full_name.replace("/", "_")
    if target.exists():
        print(f"Repositório {repo_full_name} já baixado em {target}, pulando download.")
        return target

    # Consulta a API para descobrir a branch padrão
    api_url = f"https://api.github.com/repos/{repo_full_name}"
    resp = requests.get(api_url, headers=headers)
    if resp.status_code != 200:
        raise RuntimeError(f"Falha ao obter info de {repo_full_name} ({resp.status_code})")
    default_branch = resp.json().get("default_branch", "main")

    zip_url = f"https://github.com/{repo_full_name}/archive/refs/heads/{default_branch}.zip"
    print(f"Baixando ZIP de {repo_full_name} (branch padrão: {default_branch})...")
    resp = requests.get(zip_url, headers=headers)
    if resp.status_code != 200:
        raise RuntimeError(f"Falha ao baixar {repo_full_name} ({resp.status_code})")
    
    with zipfile.ZipFile(BytesIO(resp.content)) as zf:
        zf.extractall(target)
    return target



def ensure_ck_is_built(ck_dir=CK_REPO_DIR):
    if ck_dir.exists():
        target_dir = ck_dir / "target"
        if target_dir.exists():
            jars = list(target_dir.glob("ck-*-jar-with-dependencies.jar"))
            if jars:
                print(f"Encontrado CK jar em {jars[0]}")
                return jars[0].resolve()

    if not ck_dir.exists():
        print("Clonando CK (mauricioaniche/ck)...")
        subprocess.run(["git", "clone", "https://github.com/mauricioaniche/ck", str(ck_dir)], check=True)

    mvn_exists = shutil.which("mvn") is not None
    if not mvn_exists:
        raise RuntimeError("Maven não encontrado no PATH.")

    print("Buildando CK via 'mvn clean package' ...")
    subprocess.run(["mvn", "clean", "package", "-DskipTests"], cwd=str(ck_dir), check=True)

    target_dir = ck_dir / "target"
    jars = list(target_dir.glob("ck-*-jar-with-dependencies.jar"))
    if not jars:
        raise RuntimeError("JAR do CK não encontrado após build.")
    print(f"CK jar construído: {jars[0]}")
    return jars[0].resolve()


def run_ck_on_project(ck_jar_path: Path, project_dir: Path, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "java", "-jar", str(ck_jar_path),
        str(project_dir),
        "false",  # use jars
        "0",      # max files
        "false",  # variables and fields
        str(output_dir)
    ]
    print("Executando CK:", " ".join(cmd))
    subprocess.run(cmd, check=True)


def idade_anos(iso):
    try:
        created = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - created
        return round(delta.total_seconds() / (3600 * 24 * 365), 2)
    except Exception:
        return None


from concurrent.futures import ProcessPoolExecutor, as_completed

def process_single_repo(repo, clones_dir, ck_output_base, ck_jar):
    repo_full_name = repo["nameWithOwner"]
    try:
        cloned_path = download_repo_zip(repo_full_name, clones_dir)
        # Ajusta para acessar a pasta descompactada
        extracted_subdir = next(cloned_path.iterdir())
        repo_safe_name = repo_full_name.replace("/", "_")
        ck_result_dir = ck_output_base / repo_safe_name
        run_ck_on_project(ck_jar, extracted_subdir, ck_result_dir)

        classes_csv = ck_result_dir / "classes.csv"
        if not classes_csv.exists():
            print(f"⚠️ Nenhum classes.csv para {repo_full_name}, pulando.")
            return None

        df = pd.read_csv(classes_csv)

        summary = {
            "repo": repo_full_name,
            "stars": repo.get("stargazerCount"),
            "age_years": idade_anos(repo.get("createdAt")),
            "releases": (repo.get("releases") or {}).get("totalCount"),
            "CBO_mean": df["cbo"].mean(),
            "CBO_std": df["cbo"].std(),
            "DIT_mean": df["dit"].mean(),
            "LCOM_mean": df["lcom"].mean(),
        }
        return summary
    except Exception as e:
        print(f"❌ Erro ao processar {repo_full_name}: {e}")
        return None

def process_all_repos_parallel(repos, clones_dir=CLONES_DIR, ck_output_base=CK_OUTPUT_BASE, ck_dir=CK_REPO_DIR, max_workers=4):
    try:
        ck_jar = ensure_ck_is_built(ck_dir)
    except RuntimeError as e:
        print("Erro ao preparar CK:", e)
        return

    results = []
    total_repos = len(repos)

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        future_to_repo = {executor.submit(process_single_repo, repo, clones_dir, ck_output_base, ck_jar): repo for repo in repos}

        for i, future in enumerate(as_completed(future_to_repo), start=1):
            repo = future_to_repo[future]
            repo_full_name = repo["nameWithOwner"]
            remaining = total_repos - i
            print(f"[{i}/{total_repos}] Concluído {repo_full_name} — Faltam {remaining} repositórios...")
            res = future.result()
            if res:
                results.append(res)

    results_df = pd.DataFrame(results)
    results_df.to_csv(CONSOLIDATED_CSV, index=False, encoding="utf-8")
    print(f"\n✅ Arquivo consolidado salvo em {CONSOLIDATED_CSV}")



def main():
    print("=== Lab02S02: Coleta CK em todos os repositórios ===")
    repos = fetch_top_java_repos(total=TOTAL_REPOS, per_page=PER_PAGE)
    if not repos:
        print("Nenhum repositório coletado. Abortando.")
        return
    save_repos_csv(repos, OUTPUT_REPOS_CSV)
    process_all_repos_parallel(repos, max_workers=4)



if __name__ == "__main__":
    main()
