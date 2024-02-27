from airflow.decorators import task
import pandas as pd
from sagerx import load_df_to_pg, parallel_api_calls


def create_url_list(rxcui_list:list)-> list:
    urls=[]

    for rxcui in rxcui_list:
        urls.append(f"https://rxnav.nlm.nih.gov/REST/rxclass/class/byRxcui.json?rxcui={rxcui}&relaSource=ATCPROD")
    return urls


@task()
def get_rxcuis() -> list:
    from airflow.hooks.postgres_hook import PostgresHook

    pg_hook = PostgresHook(postgres_conn_id="postgres_default")
    engine = pg_hook.get_sqlalchemy_engine()

    df = pd.read_sql(
        "select distinct rxcui from datasource.rxnorm_rxnconso where tty in ('IN', 'MIN') and sab = 'RXNORM'",
        con=engine
    )
    results = list(df['rxcui'])
    print(f"Number of RxCUIs: {results}")
    return results


@task
def extract_atc(rxcui_list:list)->None:
   # Get ATC for full list of RXCUI
    urls = create_url_list(rxcui_list)
    print(f"URL List created of length: {len(urls)}")
    atcs_list = parallel_api_calls(urls)
    print(atcs_list)
    atcs = {}

    for atc in atcs_list:
        for druginfo in atc['response']["rxclassDrugInfoList"]["rxclassDrugInfo"]:
            rxcui = druginfo["minConcept"].get("rxcui")

            atc_info = druginfo["rxclassMinConceptItem"]
            atc_info["drug_name"] = druginfo["minConcept"].get("name","")
            atc_info["drug_tty"] = druginfo["minConcept"].get("tty","") #
            atc_info["rela"] = druginfo["minConcept"].get("rela","")
            atc_info["relaSource"] = druginfo["minConcept"].get("relaSource","")            

            atcs[rxcui] = atc_info

    atc_df = pd.DataFrame.from_dict(atcs, orient='index').reset_index()

    load_df_to_pg(atc_df,"datasource","rxclass_atc_to_product","replace",index=False)
