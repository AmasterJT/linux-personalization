#include <iostream>
#include <string>
#include <vector>


using namespace std;

// Clase simple para probar
class Persona {
  public:
    string nombre;
    int edad;

    // Constructor
    Persona(string n, int e) : nombre(n), edad(e) {}

    // Método de la clase
    void saludar() const { cout << "Hola, soy " << nombre << " y tengo " << edad << " años." << endl; }
};

// Función genérica
template <typename T> T sumar(T a, T b) { return a + b; }

int main() {
    // Variables y uso de una clase
    Persona p("Juan", 30);
    p.saludar();

    // Uso de plantillas (templates)
    cout << "La suma de 5 y 10 es: " << sumar(5, 10) << endl;
    cout << "La suma de 5.5 y 2.3 es: " << sumar(5.5, 2.3) << endl;

    // Uso de vectores
    vector<int> numeros = {1, 2, 3, 4, 5};
    for (int num : numeros) {
        cout << "Número: " << num << endl;
    }

    // Manejo de excepciones
    try {
        if (numeros.size() > 10) {
            throw runtime_error("El vector es demasiado grande.");
        }
    } catch (const exception &e) {
        cout << "Error: " << e.what() << endl;
    }

    return 0;
}
