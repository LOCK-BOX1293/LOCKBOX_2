import * as vscode from "vscode";

export class HackbiteStatusBar {
  private readonly item: vscode.StatusBarItem;

  constructor() {
    this.item = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
    this.item.command = "hackbite.indexWorkspace";
    this.item.tooltip = "Hackbite backend and indexing status";
    this.item.show();
    this.setNotIndexed();
  }

  setIndexing(message = "Indexing..."): void {
    this.item.text = `$(sync~spin) Hackbite ${message}`;
    this.item.backgroundColor = undefined;
  }

  setReady(message = "Ready"): void {
    this.item.text = `$(check) Hackbite ${message}`;
    this.item.backgroundColor = undefined;
  }

  setNotIndexed(): void {
    this.item.text = "$(warning) Hackbite Not Indexed";
    this.item.backgroundColor = new vscode.ThemeColor("statusBarItem.warningBackground");
  }

  setOffline(): void {
    this.item.text = "$(error) Hackbite Backend Offline";
    this.item.backgroundColor = new vscode.ThemeColor("statusBarItem.errorBackground");
  }

  dispose(): void {
    this.item.dispose();
  }
}
