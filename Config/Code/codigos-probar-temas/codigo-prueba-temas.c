#include <stdio.h>

// Función simple que suma dos números
int sumar(int a, int b) { return a + b; }

// Estructura de datos (struct) para probar
struct Persona {
    char nombre[50];
    int edad;
};

// Función que imprime los datos de una persona
void imprimir_persona(struct Persona p) {
    printf("Nombre: %s\n", p.nombre);
    printf("Edad: %d\n", p.edad);
}

int main() {
    // Variables básicas
    int num1 = 5, num2 = 10;
    printf("La suma de %d y %d es: %d\n", num1, num2, sumar(num1, num2));

    // Condicional simple
    if (num1 < num2) {
        printf("%d es menor que %d\n", num1, num2);
    }

    // Bucle for
    for (int i = 0; i < 5; i++) {
        printf("Iteración %d\n", i);
    }

    // Crear una persona y mostrar sus datos
    struct Persona persona = {"Juan", 30};
    imprimir_persona(persona);

    return 0;
}
