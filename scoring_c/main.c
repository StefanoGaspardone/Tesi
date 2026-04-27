#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>

#define B_FLAG 1
#define B_TYPE 2
#define B_ETX 8

typedef struct {
    unsigned char *data;
    int len;
    long count;
    long score;
} Fragment;

unsigned char* load_binary_from_input_file(int argc, char *argv[], size_t *out_size);

unsigned char* load_binary_from_input_file(const int argc, char *argv[], size_t *out_size) {
    char file_name[256];
    char path[300] = "../../inputs/";

    if(argc > 1) {
        strncpy(file_name, argv[1], sizeof(file_name) - 1);
    } else {
        printf("Enter file name: ");
        scanf("%255s", file_name);
    }
    strcat(path, file_name);

    FILE *file = fopen(path, "rb");
    if(file == NULL) {
        fprintf(stderr, "The file does not exist\n");
        exit(1);
    }

    fseek(file, 0, SEEK_END);
    const size_t size = ftell(file);
    rewind(file);

    unsigned char *buffer = malloc(size);
    if(buffer == NULL) {
        fprintf(stderr, "Memory error\n");
        fclose(file);
        exit(1);
    }

    fread(buffer, 1, size, file);
    fclose(file);

    *out_size = size;
    return buffer;
}

int main(const int argc, char **argv) {
    size_t fileSize;
    unsigned char *data = load_binary_from_input_file(argc, argv, &fileSize);

    printf("%zu bytes read.\n", fileSize);

    free(data);
    return 0;
}