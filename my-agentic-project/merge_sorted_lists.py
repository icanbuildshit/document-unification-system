def merge_sorted_lists(list1, list2):
    """
    Merge two sorted lists into one sorted list.
    
    Args:
        list1 (list): First sorted list
        list2 (list): Second sorted list
        
    Returns:
        list: A new sorted list containing all elements from both lists
    """
    merged_list = []
    i = j = 0
    
    # Compare elements from both lists and add smaller one to merged list
    while i < len(list1) and j < len(list2):
        if list1[i] <= list2[j]:
            merged_list.append(list1[i])
            i += 1
        else:
            merged_list.append(list2[j])
            j += 1
    
    # Add remaining elements from list1, if any
    while i < len(list1):
        merged_list.append(list1[i])
        i += 1
    
    # Add remaining elements from list2, if any
    while j < len(list2):
        merged_list.append(list2[j])
        j += 1
    
    return merged_list


# Example usage
if __name__ == "__main__":
    list1 = [1, 3, 5, 7, 9]
    list2 = [2, 4, 6, 8, 10]
    print(f"List 1: {list1}")
    print(f"List 2: {list2}")
    merged = merge_sorted_lists(list1, list2)
    print(f"Merged list: {merged}")