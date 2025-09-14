#!/usr/bin/env python3
"""
lab02s01_automacao.py

Automação para Lab02S01:
 - Busca os top-1000 repositórios Java no GitHub (por estrelas)
 - Salva lista em lab02_repos.csv
 - Clona 1 repositório de exemplo (primeiro da lista) em clones/
 - Baixa/compila CK (se necessário) e roda CK no repositório clonado
 - Salva resultados CK em lab02_ck_results/<repo>/

Requisitos:
 - Python 3.7+
 - git no PATH
 - java (8+) no PATH
 - maven (se quiser que o script construa o JAR do CK automaticamente)
 - Definir GITHUB_TOKEN environment variable (ou editar TOKEN abaixo)

Uso:
  export GITHUB_TOKEN="ghp_..."   # ou no Windows setx ...
  python lab02s01_automacao.py
"""

import os
import sys
import time
import json
import subprocess
import shutil
from datetime import datetime, timezone
from pathlib import Path

import requests
import pandas as pd

# -----------------------
# CONFIGURAÇÕES (edite se quiser)
# -----------------------
TOKEN = "key"  # substitua ou defina GITHUB_TOKEN
GITHUB_GRAPHQL_URL = "https://api.github.com/graphql"
OUTPUT_REPOS_CSV = "lab02_repos.csv"
CLONES_DIR = Path("clones")
CK_REPO_DIR = Path("ck_tool")
CK_OUTPUT_BASE = Path("lab02_ck_results")
CK_LOCAL_JAR = CK_REPO_DIR / "target"  # a pasta onde o jar costuma ficar
CK_JAR_GLOB = "ck-*-jar-with-dependencies.jar"  # padrão de nome após build
PER_PAGE = 50    # resultados por página (max 100). 50 é OK para rate-limit.
TOTAL_REPOS = 1000
SLEEP_BETWEEN_PAGES = 1.0  # segundos
CLONE_DEPTH = 1  # use shallow clone para economizar espaço; boa para análise de fontes
# -----------------------

if TOKEN == "sua_token_aqui" or not TOKEN:
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
                print("Erro no GraphQL:", data["errors"])
                # Em caso de erro de paginação ou permission, abortamos
                raise RuntimeError(f"GraphQL errors: {data['errors']}")
            return data
        elif resp.status_code == 502 and attempt < max_retries:
            time.sleep(backoff)
            continue
        elif resp.status_code == 401:
            raise RuntimeError("401 Unauthorized — verifique seu token do GitHub.")
        else:
            # para 403 rate limit, esperar um pouco e tentar novamente
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
                  pullRequests(states: MERGED) {{ totalCount }}
                  issues {{ totalCount }}
                  closedIssues: issues(states: CLOSED) {{ totalCount }}
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
            print("⚠️ 'search' não retornado pelo GraphQL. Saindo.")
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

        # informe rate-limit (opcional)
        rl = data.get("data", {}).get("rateLimit")
        if rl:
            print(f"RateLimit remaining: {rl.get('remaining')} resetAt: {rl.get('resetAt')}")

        print(f"Página {page}: coletados até agora {collected}/{total}")
        page += 1
        if not has_next:
            print("Sem mais páginas disponíveis.")
            break
        time.sleep(SLEEP_BETWEEN_PAGES)

    return repos[:total]


def save_repos_csv(repos, filename=OUTPUT_REPOS_CSV):
    df = pd.DataFrame([{
        "nameWithOwner": r.get("nameWithOwner"),
        "url": r.get("url"),
        "createdAt": r.get("createdAt"),
        "updatedAt": r.get("updatedAt"),
        "stargazers": r.get("stargazerCount"),
        "primaryLanguage": (r.get("primaryLanguage") or {}).get("name"),
        "releases": (r.get("releases") or {}).get("totalCount"),
        "mergedPullRequests": (r.get("pullRequests") or {}).get("totalCount"),
        "issues": (r.get("issues") or {}).get("totalCount"),
        "closedIssues": (r.get("closedIssues") or {}).get("totalCount"),
    } for r in repos])
    # calcular idade em anos
    def idade_anos(iso):
        try:
            created = datetime.fromisoformat(iso.replace("Z", "+00:00"))
            delta = datetime.now(timezone.utc) - created
            return round(delta.total_seconds() / (3600 * 24 * 365), 2)
        except Exception:
            return None

    df["age_years"] = df["createdAt"].apply(idade_anos)
    df.to_csv(filename, index=False, encoding="utf-8")
    print(f"✅ Lista de repositórios salva em {filename} ({len(df)} linhas)")


def git_clone_repo(repo_full_name, dest_dir: Path, depth=1):
    repo_url = f"https://github.com/{repo_full_name}.git"
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / repo_full_name.replace("/", "_")
    if target.exists():
        print(f"Repositório {repo_full_name} já clonado em {target}, pulando clone.")
        return target
    cmd = ["git", "clone", "--depth", str(depth), repo_url, str(target)]
    print("Executando:", " ".join(cmd))
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Falha ao clonar {repo_full_name}: {e}")
    return target


def ensure_ck_is_built(ck_dir=CK_REPO_DIR):
    """
    Se a ferramenta CK não estiver compilada localmente, o script:
      - clona https://github.com/mauricioaniche/ck em ck_dir (se necessário)
      - tenta buildar com 'mvn clean package'
      - procura o jar target/*jar-with-dependencies.jar
    Retorna o caminho absoluto do JAR pronto para execução.
    """
    # 1) se jar já existe localmente (procura em ck_dir/target), usa ele
    if ck_dir.exists():
        target_dir = ck_dir / "target"
        if target_dir.exists():
            jars = list(target_dir.glob("ck-*-jar-with-dependencies.jar"))
            if jars:
                print(f"Encontrado CK jar em {jars[0]}")
                return jars[0].resolve()

    # 2) clone o repo
    if not ck_dir.exists():
        print("Clonando CK (mauricioaniche/ck)...")
        subprocess.run(["git", "clone", "https://github.com/mauricioaniche/ck", str(ck_dir)], check=True)

    # 3) tenta build com maven
    mvn_exists = shutil.which("mvn") is not None
    if not mvn_exists:
        raise RuntimeError("Maven não encontrado no PATH. Instale Maven ou construa o JAR do CK manualmente (mvn clean package).")

    print("Buildando CK via 'mvn clean package' (isso pode demorar um pouco)...")
    subprocess.run(["mvn", "clean", "package", "-DskipTests"], cwd=str(ck_dir), check=True)

    # 4) procurar jar
    target_dir = ck_dir / "target"
    jars = list(target_dir.glob("ck-*-jar-with-dependencies.jar"))
    if not jars:
        raise RuntimeError("JAR do CK não encontrado após build. Verifique o build do Maven.")
    print(f"CK jar construído: {jars[0]}")
    return jars[0].resolve()


def run_ck_on_project(ck_jar_path: Path, project_dir: Path, output_dir: Path, use_jars: bool = False):
    """
    Executa:
      java -jar ck-...jar <project dir> <use jars:true|false> <max files per partition:0> <variables and fields?:true|false> <output dir>
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    use_jars_str = "true" if use_jars else "false"
    max_files = "0"
    variables_and_fields = "false"
    cmd = [
        "java", "-jar", str(ck_jar_path),
        str(project_dir),
        use_jars_str,
        max_files,
        variables_and_fields,
        str(output_dir)
    ]
    print("Executando CK:", " ".join(cmd))
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Falha ao executar CK: {e}")
    print(f"✅ CK finalizado. Resultados em {output_dir}")


def gather_ck_sample_csv(output_dir: Path, sample_output_csv: Path):
    """
    O CK gera normalmente arquivos: "classes.csv", "methods.csv", "variables.csv".
    Aqui copiamos classes.csv para sample_output_csv (ou combinamos se necessário).
    """
    classes_csv = output_dir / "classes.csv"
    if not classes_csv.exists():
        # tenta encontrar qualquer csv no output_dir
        any_csvs = list(output_dir.glob("*.csv"))
        if not any_csvs:
            raise RuntimeError(f"Nenhum CSV gerado pelo CK em {output_dir}")
        # pega o primeiro
        classes_csv = any_csvs[0]
    shutil.copy(str(classes_csv), str(sample_output_csv))
    print(f"Arquivo de amostra do CK salvo em {sample_output_csv}")


def main():
    print("=== Lab02S01: coletando top Java repos e rodando CK em 1 repositório (exemplo) ===")
    print("1) Buscando lista de repositórios (pode demorar alguns minutos)...")
    repos = fetch_top_java_repos(total=TOTAL_REPOS, per_page=PER_PAGE)
    if not repos:
        print("⚠️ Nenhum repositório coletado. Abortando.")
        return
    save_repos_csv(repos, OUTPUT_REPOS_CSV)

    # clonando o primeiro repositório (exemplo)
    first = repos[0]
    repo_full_name = first["nameWithOwner"]
    print(f"\n2) Clonando o repositório exemplo: {repo_full_name}")
    cloned_path = git_clone_repo(repo_full_name, CLONES_DIR, depth=CLONE_DEPTH)
    print("Clonado em:", cloned_path)

    # prepara o CK (download/build)
    print("\n3) Preparando CK (build se necessário)...")
    try:
        ck_jar = ensure_ck_is_built(CK_REPO_DIR)
    except RuntimeError as e:
        print("⚠️ Erro ao preparar CK:", e)
        print("Se preferir, faça build manualmente: clone https://github.com/mauricioaniche/ck e rode 'mvn clean package', então atualize CK_REPO_DIR.")
        return

    # rodar CK no repositório clonado
    repo_safe_name = repo_full_name.replace("/", "_")
    ck_result_dir = CK_OUTPUT_BASE / repo_safe_name
    print(f"\n4) Executando CK no repositório {repo_full_name} ...")
    run_ck_on_project(ck_jar, cloned_path, ck_result_dir, use_jars=False)

    # copiar o CSV de classes como amostra
    sample_csv = Path(f"lab02_ck_sample_{repo_safe_name}.csv")
    gather_ck_sample_csv(ck_result_dir, sample_csv)

    print("\n=== FIM ===")
    print(f"- Repositórios listados: {OUTPUT_REPOS_CSV}")
    print(f"- Repositório clonado (exemplo): {cloned_path}")
    print(f"- Resultados CK: {ck_result_dir}")
    print(f"- Amostra CK (CSV): {sample_csv}")


if __name__ == "__main__":
    main()
