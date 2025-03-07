from airflow.decorators import task
import pandas as pd
from sagerx import get_rxcuis, load_df_to_pg, get_concurrent_api_results, write_json_file, read_json_file, create_path
from common_dag_tasks import get_data_folder
import logging

def create_url_list(rxcui_list:list)-> list:
    urls=[]

    for rxcui in rxcui_list:
        urls.append(f"https://rxnav.nlm.nih.gov/REST/rxclass/class/byRxcui.json?rxcui={rxcui}")
    return urls

@task
def extract(dag_id:str) -> str:
    """
    Retrieves RxClass concepts from RxNav for the EPC class type,
    processes them concurrently, and loads results into Postgres.
    """
    logging.info("Starting data retrieval for RxClass...")

    # 1. Fetch the list of concepts
    tty_list = ['IN','PIN','MIN','SCDC','SCDF','SCDFP','SCDG','SCDGP','SCD','GPCK','BN','SBDC','SBDF','SBDFP','SBDG','SBD','BPCK']
    #tty_list = ['SCD', 'SBD', 'GPCK', 'BPCK']
    #tty_list = ['BPCK']
    rxcui_list = get_rxcuis(tty_list, active_only = True)
    logging.info(f"Fetched {len(rxcui_list)} RXCUIs.")

    # 1.5. Create list of urls
    url_list = create_url_list(rxcui_list)

    results = get_concurrent_api_results(url_list)

    data_folder = get_data_folder(dag_id)
    file_path = create_path(data_folder) / 'data.json'
    file_path_str = file_path.resolve().as_posix()

    write_json_file(file_path_str, results)

    print(f"Extraction Completed! Data saved to file: {file_path_str}")

    return file_path_str


@task
def load(file_path_str:str):
    results = read_json_file(file_path_str)

    classes = []
    for result in results:
        response = result['response']
        if 'rxclassDrugInfoList' in response:
            for drug_info in response["rxclassDrugInfoList"]["rxclassDrugInfo"]:
                classes.append(
                    dict(
                        rxcui = drug_info["minConcept"].get("rxcui"),
                        name = drug_info["minConcept"].get("name",""),
                        tty = drug_info["minConcept"].get("tty",""),
                        rela = drug_info.get("rela",""),
                        class_id = drug_info["rxclassMinConceptItem"].get("classId",""),
                        class_name = drug_info["rxclassMinConceptItem"].get("className",""),
                        class_type = drug_info["rxclassMinConceptItem"].get("classType",""),
                        rela_source = drug_info.get("relaSource","")            
                    )
                )
    df = pd.DataFrame(classes).drop_duplicates()
    print(f'Dataframe created of {len(df)} length.')
    load_df_to_pg(df,"sagerx_lake","rxclass","replace",index=False)
