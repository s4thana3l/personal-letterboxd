from typing import Protocol


# w Define o contrato que qualquer catálogo externo precisa implementar.
class MovieProvider(Protocol):
    def validate_query(self, query: str) -> str:
        ...

    def validate_imdb_id(self, imdb_id: str) -> str:
        ...

    def search(self, query: str) -> list[dict]:
        ...

    def get_movie(self, imdb_id: str) -> dict | None:
        ...
