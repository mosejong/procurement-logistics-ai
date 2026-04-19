from urllib.parse import unquote


def normalize_service_key(service_key: str) -> str:
    """
    공공데이터포털 서비스키는 인코딩된 키와 디코딩된 키가 섞여 쓰인다.
    requests params에 넣을 때는 원문 키를 쓰되, 비교와 로그 확인에는 정규화된 값을 사용할 수 있다.
    """
    return unquote(service_key or "")
