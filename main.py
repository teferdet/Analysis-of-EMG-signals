from src.GUI import GUI

def main():
    # Will add logging
    gui = GUI()
    gui.mainloop()

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print("Sorry something went wrong")