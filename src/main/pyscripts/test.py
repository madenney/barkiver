
print("hello world")

def main():
  f = open("/home/matt/Projects/output/test.txt", "a")
  f.write("\nhello hello hello")
  f.close()

if __name__ == '__main__':
    main()
