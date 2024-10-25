import os
import pandas as pd

# Caminho relativo para o arquivo dentro da pasta 'data'
caminho_arquivo = 'data/arquivo.csv'

# Verificar se o arquivo existe
if os.path.exists(caminho_arquivo):
    df = pd.read_csv(caminho_arquivo)
    print("Arquivo carregado com sucesso.")
    print("Colunas do DataFrame:", df.columns)
    print(df.head())  # Mostrar as primeiras linhas do DataFrame
else:
    print("Arquivo não encontrado no caminho especificado.")
