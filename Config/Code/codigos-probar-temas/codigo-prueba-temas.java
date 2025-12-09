import java.util.ArrayList;

// Clase simple para probar
class Persona {
    private String nombre;
    private int edad;

    // Constructor
    public Persona(String nombre, int edad) {
        this.nombre = nombre;
        this.edad = edad;
    }

    // Método de la clase
    public void saludar() {
        System.out.println("Hola, soy " + nombre + " y tengo " + edad + " años.");
    }
}

class Main {
    public static void main(String[] args) {
        // Crear una instancia de Persona y usar su método
        Persona persona = new Persona("Juan", 30);
        persona.saludar();

        // Uso de una lista (ArrayList)
        ArrayList<Integer> numeros = new ArrayList<>();
        numeros.add(1);
        numeros.add(2);
        numeros.add(3);

        // Bucle for-each
        for (int num : numeros) {
            System.out.println("Número: " + num);
        }

        // Condicional simple
        int num1 = 10, num2 = 20;
        if (num1 < num2) {
            System.out.println(num1 + " es menor que " + num2);
        }

        // Manejo de excepciones
        try {
            int resultado = num1 / 0;
            System.out.println(resultado);
        } catch (ArithmeticException e) {
            System.out.println("Error: " + e.getMessage());
        }
    }
}
