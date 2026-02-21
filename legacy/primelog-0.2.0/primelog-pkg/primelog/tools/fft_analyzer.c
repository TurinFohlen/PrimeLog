#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include <string.h>
#include <ctype.h>

#define MAX_POINTS 1024

typedef struct {
    double real;
    double imag;
} complex;

// FFT 算法（基2，支持正变换和逆变换）
void fft(complex *x, int n, int inverse) {
    if (n <= 1) return;
    int j = 0;
    for (int i = 0; i < n; i++) {
        if (j > i) {
            complex tmp = x[i];
            x[i] = x[j];
            x[j] = tmp;
        }
        int m = n >> 1;
        while (j >= m && m > 0) {
            j -= m;
            m >>= 1;
        }
        j += m;
    }
    for (int len = 2; len <= n; len <<= 1) {
        double ang = 2 * M_PI / len * (inverse ? 1 : -1);
        complex wlen = { cos(ang), sin(ang) };
        for (int i = 0; i < n; i += len) {
            complex w = { 1, 0 };
            for (int j = 0; j < len/2; j++) {
                complex u = x[i + j];
                complex v = {
                    x[i + j + len/2].real * w.real - x[i + j + len/2].imag * w.imag,
                    x[i + j + len/2].real * w.imag + x[i + j + len/2].imag * w.real
                };
                x[i + j].real = u.real + v.real;
                x[i + j].imag = u.imag + v.imag;
                x[i + j + len/2].real = u.real - v.real;
                x[i + j + len/2].imag = u.imag - v.imag;

                complex w_tmp = {
                    w.real * wlen.real - w.imag * wlen.imag,
                    w.real * wlen.imag + w.imag * wlen.real
                };
                w = w_tmp;
            }
        }
    }
    if (inverse) {
        for (int i = 0; i < n; i++) {
            x[i].real /= n;
            x[i].imag /= n;
        }
    }
}

// 从文件中读取数值（每行一个数字）
int read_times(const char *filename, double *times, int max) {
    FILE *fp = fopen(filename, "r");
    if (!fp) return -1;
    char line[256];
    int count = 0;
    while (fgets(line, sizeof(line), fp) && count < max) {
        times[count] = atof(line);
        count++;
    }
    fclose(fp);
    return count;
}

void show_help(const char *prog_name) {
    printf("用法: %s analyze <数值文件>\n", prog_name);
    printf("  对数值序列进行 FFT 分析，输出幅度谱（频率系数 1 到 N/2-1）。\n");
    printf("示例: %s analyze intervals.txt\n", prog_name);
}

int analyze(const char *filename) {
    double times[MAX_POINTS];
    int n = read_times(filename, times, MAX_POINTS);
    if (n <= 0) {
        fprintf(stderr, "错误: 无法读取数据或文件为空\n");
        return 1;
    }

    int fft_n = 1;
    while (fft_n < n) fft_n <<= 1;

    complex *x = malloc(fft_n * sizeof(complex));
    if (!x) {
        fprintf(stderr, "内存分配失败\n");
        return 1;
    }

    // 去直流
    double mean = 0;
    for (int i = 0; i < n; i++) mean += times[i];
    mean /= n;

    for (int i = 0; i < fft_n; i++) {
        if (i < n) {
            x[i].real = times[i] - mean;
            x[i].imag = 0.0;
        } else {
            x[i].real = x[i].imag = 0.0;
        }
    }

    fft(x, fft_n, 0);

    printf("--- FFT 分析结果 (%d 点) ---\n", fft_n);
    printf("频率系数\t幅度\n");
    for (int k = 1; k < fft_n/2; k++) {
        double mag = sqrt(x[k].real * x[k].real + x[k].imag * x[k].imag) / fft_n;
        if (mag > 0.001) {
            printf("%d\t\t%.6f\n", k, mag);
        }
    }

    free(x);
    return 0;
}

int main(int argc, char **argv) {
    if (argc < 2) {
        show_help(argv[0]);
        return 1;
    }

    if (strcmp(argv[1], "analyze") == 0) {
        if (argc < 3) {
            fprintf(stderr, "错误: analyze 命令需要指定文件路径\n");
            return 1;
        }
        return analyze(argv[2]);
    } else if (strcmp(argv[1], "help") == 0 || strcmp(argv[1], "--help") == 0) {
        show_help(argv[0]);
    } else {
        fprintf(stderr, "未知命令: %s\n", argv[1]);
        show_help(argv[0]);
        return 1;
    }
    return 0;
}