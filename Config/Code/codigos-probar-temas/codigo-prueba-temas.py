# Este es un comentario de una sola línea

"""
Este es un comentario multilinea
utilizado generalmente para documentar funciones o clases.
"""

# Definición de una función simple
def funcion_prueba(param1, param2=42):
    """
    Función de prueba que realiza una operación matemática y muestra el resultado.

    Args:
        param1 (int, float): El primer parámetro.
        param2 (int, float, opcional): El segundo parámetro (por defecto es 42).

    Returns:
        float: El resultado de la operación.
    """
    resultado = param1 + param2
    print(f"Resultado de la suma: {resultado}")
    return resultado

# Clase de prueba para probar visualización de clases
class MiClase:
    variable_clase = "Hola, soy una clase"

    def __init__(self, valor):
        self.valor = valor

    def metodo(self):
        """
        Este método imprime el valor de la instancia.
        """
        print(f"El valor es {self.valor}")

# Uso de condicionales
def prueba_condicionales(valor):
    if valor > 10:
        print("El valor es mayor que 10")
    elif valor == 10:
        print("El valor es exactamente 10")
    else:
        print("El valor es menor que 10")

# Uso de ciclos
def prueba_ciclos():
    for i in range(5):
        print(f"Índice en el ciclo: {i}")

    while True:
        respuesta = input("¿Salir del ciclo? (s/n): ")
        if respuesta.lower() == 's':
            break

# Función lambda y map
suma_cuadrados = lambda x, y: x**2 + y**2

numeros = [1, 2, 3, 4]
cuadrados = list(map(lambda x: x**2, numeros))

# Manejo de excepciones
def manejo_excepciones():
    try:
        resultado = 10 / 0
    except ZeroDivisionError as e:
        print(f"Error: {e}")
    finally:
        print("Finalizó el bloque de manejo de excepciones")

# Entrada principal
if __name__ == "__main__":
    resultado = funcion_prueba(10)
    mi_objeto = MiClase("Valor inicial")
    mi_objeto.metodo()

    prueba_condicionales(15)
    prueba_ciclos()

    print(f"Suma de cuadrados: {suma_cuadrados(3, 4)}")
    print(f"Cuadrados de los números: {cuadrados}")

    manejo_excepciones()
